"""Mechanical test-deletion guard.

The cheapest way to make a red suite look green is to delete or comment out the test
that fails. A green-command receipt can't see that — the suite really did pass, because
the failing test is gone. This module reads the task's diff and blocks marking a task
passing when it *removes test functions on net*: the count of test-function definitions
added must be >= the count removed (across files that look like tests).

This is a high-precision guard, not a coverage tool. Whether a *new* behavior has a
*meaningful* test is a judgment call — that lives in the review rubric's Tests lane, not
here. Legitimately removing an obsolete test is allowed by marking the task with
`"allow_test_removal": true`, or by turning the guard off with `[gate] guard_test_deletion
= false` in the ## Temper block.
"""

from __future__ import annotations

import fnmatch
import re
from pathlib import Path

from . import evidence

# Default globs for "this file is a test". Override with [gate] test_globs in config.
DEFAULT_TEST_GLOBS = (
    "**/test_*.py", "**/*_test.py", "**/tests/**", "**/test/**",
    "**/*.test.*", "**/*.spec.*", "**/*_test.go",
)

# Patterns that define a single test case (not a group/suite). Language-spread, deliberately
# conservative: a line must *define* a test for it to count.
_TEST_DEFS = re.compile(
    r"(\bdef\s+test\w*\s*\()"      # python: def test_...(
    r"|(\bfunc\s+Test\w*\s*\()"    # go: func TestXxx(
    r"|(\b(it|test)\s*\()"         # js/ts: it(...) / test(...)
    r"|(@(Test|ParameterizedTest)\b)"  # jvm: @Test
)


def is_test_file(path: str, globs) -> bool:
    p = path.lstrip("ab/").lstrip("/")
    return any(fnmatch.fnmatch(p, g) or fnmatch.fnmatch("/" + p, g) for g in globs)


def test_function_delta(diff: str, globs=DEFAULT_TEST_GLOBS) -> int:
    """(test-defs added) - (test-defs removed), counted only inside test files.
    Negative => the diff removes tests on net."""
    added = removed = 0
    in_test_file = False
    for line in diff.splitlines():
        if line.startswith("+++ "):
            # "+++ b/path/to/file" — the new-side path names the file for the hunk.
            path = line[4:].strip()
            in_test_file = path != "/dev/null" and is_test_file(path, globs)
            continue
        if line.startswith("--- ") or line.startswith("diff ") or line.startswith("@@"):
            continue
        if not in_test_file:
            continue
        if line.startswith("+") and _TEST_DEFS.search(line[1:]):
            added += 1
        elif line.startswith("-") and _TEST_DEFS.search(line[1:]):
            removed += 1
    return added - removed


def regressions(project_root: str | Path, globs=DEFAULT_TEST_GLOBS) -> list[str]:
    """Problem strings if the current diff removes tests on net; empty if clean."""
    diff = evidence.working_diff(project_root)
    delta = test_function_delta(diff, globs)
    if delta < 0:
        return [
            f"the diff removes {-delta} more test(s) than it adds — a deleted/weakened test is the "
            f"classic way to fake green. Restore the test, or (if the removal is legitimate) set "
            f'"allow_test_removal": true on the task or [gate] guard_test_deletion = false.'
        ]
    return []
