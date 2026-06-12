# Review Rubric — Thermo-Nuclear Code Quality

Encodes the cursor `thermo-nuclear-code-quality-review` skill as the standard for
this harness's review stage. The review runs in a **fresh context** (separate from
the agent that wrote the code) so the judge is not the author.

## Purpose
A brutally strict audit for **structural maintainability**, not cosmetics. It
prioritizes ambitious restructuring that simplifies the implementation while
preserving behavior. Bias toward cleaning the design, not rubber-stamping working
code.

## Seven non-negotiable standards
1. Push for structural simplification — hunt for "code judo" moves that delete whole branches.
2. Files crossing **~1000 lines** are a strong smell requiring decomposition.
3. Ad-hoc conditionals scattered through code are design failures.
4. Bias toward cleaning the design, not approving merely-working code.
5. Prefer direct, boring, maintainable code over clever patterns.
6. Enforce type/boundary cleanliness; question unnecessary optionality.
7. Keep logic canonical; reuse existing helpers instead of duplicating them.

## Ask of each meaningful change
- Is there a code-judo move that makes this dramatically simpler?
- Did the diff push a file past healthy size boundaries?
- Did it leak feature-specific logic into shared paths?

## Severity order (report highest first)
1. Structural regressions
2. Dramatic simplification opportunities
3. Branching-complexity increases
4. Boundary / abstraction problems
5. File-size concerns
6. Modularity issues
7. Legibility concerns

## Presumptive approval blockers (reject unless justified)
- Preserving incidental complexity when a simpler path exists
- Pushing a file above ~1000 lines
- Adding ad-hoc branching to existing flows
- Scattering feature checks across shared code
- Introducing unnecessary abstractions or cast-heavy contracts
- Duplicating existing helpers or misplacing logic

## Output
- High-conviction findings over nits; fewer comments, larger structural impact.
- Direct, serious tone without rudeness; every finding actionable.
- Emit a verdict file `.temper/eval_feedback/<task>.json`:
  `{ "task": "T1", "verdict": "pass" | "block", "findings": [ {"severity": "...", "where": "...", "what": "...", "fix": "..."} ] }`.
- `verdict: "block"` means the task must not be marked passing until the blocking
  findings are resolved — the same bar as a failing receipt.
