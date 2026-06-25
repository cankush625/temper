# Review Rubric — Thermo-Nuclear, superset

The standard Temper applies at the review gate. It is a **superset**: the structural
depth of cursor's `thermo-nuclear-code-quality-review` skill **plus** every concern a
strict instruction-level review (clean-code rules + TDD discipline + a concern-by-concern
audit) would raise — so a PR that clears this rubric has nothing legitimate left for such a
review to flag. The review runs in a **fresh context** (separate from the agent that
wrote the code) so the judge is not the author, and its verdict is recorded as a
**signed, tree-pinned receipt** (`temper review-capture`), not a claim.

## Purpose
A brutally strict audit for **structural maintainability and correctness**, not
cosmetics. Bias toward cleaning the design and catching real failure modes over
rubber-stamping working code. Every finding must name a **concrete impact** — if you
can't, downgrade or drop it.

## Lanes — review by concern, not by file
Run all that apply to the diff. The first lane is Temper's structural core; the rest are
the coverage that makes this a superset.

1. **Structure & simplification** (the thermo-nuclear core)
   - Hunt "code judo" moves that delete whole branches while preserving behavior.
   - Files crossing **~1000 lines** are a strong smell requiring decomposition.
   - Ad-hoc conditionals scattered through shared paths are design failures.
   - Prefer direct, boring, maintainable code over clever patterns.
   - Question unnecessary optionality and cast-heavy contracts; keep logic canonical
     (reuse existing helpers, don't duplicate).
   - Bloat patterns: *wrong weight class* (a heavy dep where a stdlib/native idiom fits),
     *premature abstraction* (indirection before the second concrete case),
     *speculative defense* (handling states the call sites can't produce),
     *ceremony without value* (wrappers that add no behavior or clarity).
2. **Correctness** — business-logic errors, missed edge cases, data/query correctness,
   off-by-one, wrong defaults, unhandled None/empty/error returns.
3. **Security** — parameterized queries (never string-concat SQL); no hardcoded secrets
   (env/vault); never log secrets/PII; authz checks on protected paths.
   **Secret scan**: flag committed credential patterns as **Must fix**.
4. **Migration safety** (if the diff has DB migrations) — destructive ops without a path
   back (`DROP COLUMN`, `NOT NULL` without default, unbatched bulk `UPDATE`) → Must fix;
   missing backfill for non-nullable columns → Must fix; no `downgrade()`/rollback → Should fix.
5. **Performance** — concrete modes, not micro-opts: N+1 / per-row query in a loop where a
   batched fetch is idiomatic; repeated work in a hot path with a sensible cache scope;
   sync I/O or CPU-bound work on an async runtime without offload; allocation in a hot path;
   missing index on a query the diff adds (when the schema sits in the same PR).
6. **Conventions** (drift guard) — booleans named `is/has/should/can/will` (not bare
   adjectives); one word per concept (don't mix `fetch`/`get`/`retrieve`); ≤3 params
   (else an options object); no boolean params (split or options); errors never swallowed
   silently; error messages carry context (what was attempted, what failed, why).
   **Docstrings** follow [`code-style.md`](code-style.md): a public function/class/method has a
   docstring with one example, delimiters on their own lines. Missing docstring/example on a
   public symbol → Should fix; layout nits → Nice to have. Applies to new/modified code only.
7. **Tests** — *meaningfulness over coverage*: a new business rule / branch must have a test
   that actually exercises it; assertions verify outcomes, not just that keys exist; mocks
   not stacked so deep the test checks wiring instead of behavior; error/edge paths tested as
   hard as happy paths. A test deleted or weakened to make the suite green is **Must fix**.
   **Test placement (every project):** a source file's tests belong in the single existing
   `test_<source>.py` (the project's established convention/framework). New tests must be
   **appended to that existing file** — a new test file when one already exists, or any other
   naming scheme (`<name>_test.py`, `tests_<name>.py`, parallel/ad-hoc files), is **Must fix**.
8. **Intent & coverage** — does the change fully satisfy the ticket/PR description? Read the
   code to form your own understanding of the business logic, compare against the stated
   intent; if they diverge, flag it. Missing requirements, unhandled acceptance criteria, or
   scope creep are findings.
9. **Pattern conformance** — compare against how *this* codebase handles similar concerns
   (naming, tests, monitoring, config), not generic best practices.
10. **API docs** — new route handlers get stack-appropriate annotation (e.g. FastAPI
    `response_model` + docstring) when the project documents an API surface → Should fix.

## Finding shape
Each finding states: **What** is wrong · **Where** (`file:line`) · **Impact** (concrete
failure mode or cost — not "bad practice") · **Value if fixed** (what improves) ·
**Suggested fix**. High-conviction findings over nits; fewer comments, larger impact.
Direct and serious in tone, never rude. Every finding actionable.

## Severity tiers
`Must fix` · `Should fix` · `Open question` · `Nice to have`. A `Nice to have` must say
"no functional impact" so the reader knows it's optional. Report highest severity first.

## Verdict
The verdict is **block** if any `Must fix` **or `Should fix`** finding is present, else **pass**.
Both tiers are blocking toward a PR merge — the severity tier *is* the blocking signal, so a
finding you judge genuinely non-blocking belongs in `Open question` or `Nice to have`, not in
`Should fix` with a `pass`. A blocked review is the same bar as a failing receipt: the task must
not be marked passing until the blocking findings are resolved and review is re-run on the fixed
code. This is enforced mechanically — `review-capture` **coerces a `pass` to `block`** when the
findings carry any `Must fix`/`Should fix`, so the verdict can never contradict its own findings.

Record it as a signed receipt (never hand-write the JSON):
```
temper review-capture --in verdict.json     # or: pipe the verdict JSON on stdin
```
where `verdict.json` is:
```json
{
  "task": "T1",
  "verdict": "pass",
  "reviewer": "<reviewing agent/context id>",
  "summary": "one-line gist",
  "findings": [
    {"severity": "Must fix", "where": "path:line", "what": "...",
     "impact": "...", "value": "...", "fix": "..."}
  ]
}
```
`review-capture` pins the verdict to the current code state and exits 0 on pass / 1 on
block. If the code changes afterward the receipt goes stale and review must be re-run —
exactly like a test. This is what makes Temper's review **enforced**, not advisory.

## Do not
- Do not rubber-stamp merely-working code.
- Do not propose rewrites that change behavior; simplifications must preserve behavior.
- Do not invent findings to look thorough — a finding with no concrete impact is noise.
