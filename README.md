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
- Code style (docstring format, conventions) → [`docs/code-style.md`](docs/code-style.md)
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
| `/tp-learn` | Distill this session's lessons into learned skills now (a background reflection when the turn ends), instead of waiting for the automatic one. |

---

## The session workflow (`/tp-impl`)

One task per session, in order — defined in [`skills/temper/SKILL.md`](skills/temper/SKILL.md):

1. **Orient** — start from the ledger summary the session-start hook injected, then read `.temper/progress.md`, the plan, `git log -5`, and the `## Temper` block.
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

What lands on disk is **redacted** (`lib/redact.py`, rules in `lib/redaction_rules.toml`): the
command line, the claim and the output tails have secrets (cloud keys, tokens, private keys,
credentials in URLs or `key=value` pairs) and personal data (emails, phone and card numbers)
replaced with `[REDACTED:<category>:<name>]`. The output streamed to your terminal is untouched,
and `stdout_sha256` is taken over the raw output, so the receipt still pins exactly what ran.
Review receipts redact their summary and findings the same way. Redaction is pattern-based and
best-effort: it catches the shapes it knows.

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
| `session_start.py` (SessionStart) | opens each session with a short ledger summary: each plan's progress and next open task, passing claims the Stop hook would reject now, and the last few gate blocks (logged to `.temper/gate_log.jsonl`) | starting blind — re-claiming stale work, repeating a refused move |

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

### Learning loop (skills learned from your sessions)
Lessons a session teaches — a correction you gave, a technique that worked, a learned skill that
turned out wrong — are distilled into Claude Code skills automatically, kept consolidated, and
retired when unused. Temper only ever touches skills it created.

| Piece | What it does |
|---|---|
| **Trigger** (`hooks/learn.py`, Stop) | After each turn, reads the new transcript bytes: counts tool calls, user prompts (requests) and learned-skill loads. Every `reflect_every` tool calls (or after `/tp-learn`) it writes the **redacted** episode and starts a detached worker. Never blocks the session. |
| **Reflector** (`prompts/learn-reflector.md`) | A headless `claude -p` child on `model` (default Haiku): Read/Grep/Glob only, no MCP, user settings only (Temper's project hooks don't run in it), no saved session, hard `--max-budget-usd` cap, JSON-schema output. It **proposes** create / update / patch / archive intents — it cannot write. |
| **Promoter** (`lib/promoter.py`) | The only writer. Lands an intent atomically or rejects it with a reason: kebab-case name (`tl-<name>`); only skills holding Temper's marker can be changed; frontmatter with a one-line `description` and a `category`; ≤40 lines / 8 KB; a safety scan (`lib/skill_guard.py`) that also rejects anything weakening Temper's rails (`--no-verify`, force-push, amend, skipping permissions, touching `.temper/` evidence); nothing the redactor would change; no project paths in a global skill. **The intent's evidence must appear verbatim in the episode** — a lesson must point at something that happened. |
| **Curator** (`prompts/learn-curator.md`) | Every `consolidate_every` tool calls, folds near-duplicate skills under class-level ones. Snapshots both skill trees first; a folded skill is archived with `absorbed_into`. |
| **Lifecycle** (`lib/lifecycle.py`) | At session start: a skill's rate is loads over requests since it was created. New skills sit in probation (`maturity_*` requests); at maturity a never-loaded skill is archived; over `capacity_*`, the lowest rates go. Archive = a folder move, never a delete. |
| **Index** (`hooks/session_start.py`) | Each session opens with the learned skills grouped by category, plus one line on the last run — including what the promoter rejected and why. |

Skills land in `.claude/skills/tl-<name>/` (project — git-excluded by `temper init`) or
`~/.claude/skills/tl-<name>/` (global — preferences and general techniques). Each carries
`.temper-learned.json` (marker + counters), an append-only `.ledger.jsonl` (why it was created or
changed), and `references/evidence-*.md` (the verbatim slice behind each entry). Run accounts are in
`.temper/learn/runs/`; `temper learn status` prints the index and the last run.

Tune it under `[learn]` in the `## Temper` block (all optional; defaults shown):

```toml
[learn]
enabled = true            # false turns the loop and the index off
reflect_every = 50        # tool calls between reflections
consolidate_every = 250   # tool calls between curator passes
model = "haiku"
max_budget_usd = 0.50     # hard cap per background run
global = true             # allow skills in ~/.claude/skills
maturity_project = 100    # probation, in requests
maturity_global = 300
capacity_project = 50     # mature skills kept per layer
capacity_global = 20
```

**Cost:** one capped Haiku run per `reflect_every` tool calls and one per `consolidate_every`; a
measured reflection on a short episode cost under $0.01. Set `enabled = false` to stop it.

---

## Repository layout
```
docs/      best-practices.md · anti-bluffing.md · review-rubric.md · safety.md · commit-style.md · code-style.md · research/
commands/  tp-init · tp-plan · tp-impl · tp-review · tp-swarm · tp-cleanup · tp-learn   (slash commands)
skills/    temper/ (session protocol) · temper-review/ (thermo-nuclear)
hooks/     capture.py · review_capture.py · evidence_gate.py · session_integrity.py · session_start.py · learn.py
lib/       evidence.py · plan_schema.py · config.py · claude_md.py · detect.py · test_evidence.py
           redact.py (+ redaction_rules.toml) · gate_log.py
           transcript.py · skill_store.py · skill_guard.py · promoter.py · learn_state.py · lifecycle.py
prompts/   learn-reflector.md · learn-curator.md · skill-format.md   (learning-loop child prompts)
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
- Merges the four hooks (`evidence_gate`, `session_integrity`, `session_start`, `learn`) into `<project>/.claude/settings.local.json` by absolute path — the
  personal, gitignored file (higher precedence than the shared `settings.json`), since the hook
  command is machine-specific. **Never** writes the shared `settings.json`; migrates hooks a
  prior init left there, and won't duplicate hooks on re-run.
- Scaffolds `<project>/.temper/` (`plans/`, `progress.md`, `.gitignore` for the signing key).
- Ensures a `## Temper` block exists in **`CLAUDE.local.md`** (personal, uncommitted) — never
  the shared `CLAUDE.md`. Runs detection to seed it if absent.
- Excludes its own machine-specific footprint from git locally (`.git/info/exclude`): `.temper/`,
  `CLAUDE.local.md`, `.claude/settings.local.json`, the `.claude/commands/tp-*.md` symlinks, and
  the `.claude/skills/temper{,-review}` symlinks — by exact name/glob, never `.claude/` wholesale,
  so a team can still commit their own `.claude/` content. Nothing Temper writes pollutes the repo.

`temper init <project> --dry-run` runs detection only and prints the block — no wiring.
(A remote updater for the engine itself — rustup/nvm-style — would be a separate `temper sync`,
not part of `init`; it's deferred.)

---

## Tests

Standard library only, no install step:

```bash
python3 -m unittest discover -s tests -t .
```

Tests mirror the source path: `lib/redact.py` → `tests/lib/test_redact.py`.

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
Learned skills are model-written: the promoter's checks are deterministic, but the safety scan is
pattern matching and the evidence check proves only that a lesson quotes the session, not that the
lesson is right. A learned skill never overrides `docs/safety.md` or the gates.

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
`thermo-nuclear-code-quality-review`; file skeleton inspired by `celesteanders/harness`; the learning loop's shape from
`tigerless-labs/autoharness`. See
[`docs/research/sources.md`](docs/research/sources.md).
