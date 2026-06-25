# Code Style

Conventions for code written under Temper. Lane 6 ("Conventions") of the
[review rubric](review-rubric.md) checks these; this file is the detail behind it.

## Docstrings (functions, classes, methods)

Every public function, class, and method carries a docstring, formatted the same shape in
every language: the **opening delimiter alone on its own line**, content from the **next**
line, the **closing delimiter alone on the last line**, and **one worked example**.

### Python — the canonical form

- The docstring is the **first statement** in the body — immediately after the `def`/`class`
  line, with nothing in between.
- The opening `"""` sits **alone on the first line** — no summary text, no comment beside it.
- Content (the summary and the rest) starts on the **second** line.
- The closing `"""` is **alone on the last line** of the docstring.
- Exactly **one blank line** separates the docstring from the code that follows it.
- Include **one example**.

```python
def add(a: int, b: int) -> int:
    """
    Return the sum of two integers.

    Example:
        >>> add(2, 3)
        5
    """

    return a + b
```

Class:

```python
class Counter:
    """
    A mutable integer counter that starts at zero.

    Example:
        >>> c = Counter()
        >>> c.increment()
        >>> c.value
        1
    """

    def __init__(self) -> None:
        self.value = 0
```

> Note: the trailing blank line conflicts with some Python doc linters (e.g. pydocstyle /
> ruff `D202`, "no blank line after function docstring"). If you run that check, disable
> `D202` so the linter and this rule agree.

### Other languages — same shape, native placement

Go and JS/TS attach the doc comment **above** the declaration, not inside the body. There the
"blank line before the code" inverts: the doc block sits **directly against** the declaration —
a blank line between them detaches it (godoc and JSDoc both require adjacency). What carries
across every language: a doc block is present, its delimiters/markers stand on their own lines,
and it contains one example.

Go (doc comment is `//` lines immediately above the declaration, no blank line before `func`):

```go
// Add returns the sum of two integers.
//
// Example:
//
//	Add(2, 3) // => 5
func Add(a, b int) int {
	return a + b
}
```

JavaScript / TypeScript (JSDoc block immediately above the declaration):

```js
/**
 * Return the sum of two integers.
 *
 * @example
 * add(2, 3); // => 5
 */
function add(a, b) {
  return a + b;
}
```

## Severity at review

Missing docstring or missing example on a public symbol → **Should fix**. Layout deviations
(delimiter placement, the blank-line separation) → **Nice to have** unless they genuinely hurt
readability. Recall that both `Must fix` and `Should fix` block a merge — so reserve the
blocking tiers for *missing* docs, not formatting nits.

## Scope

This rule applies to **new and modified** code. The Python already in this repo predates it and
uses the one-line-summary form; bulk-reformatting the existing tree is a separate, opt-in task.
