"""Per-project config: the verify commands Temper runs for a repo.

Sourced from a fenced ```toml block under `## Temper` in the project's CLAUDE.md
(see lib/claude_md.py) — Temper never hardcodes pytest/terraform, and there is no
separate config file to drift from the docs.
"""

from __future__ import annotations

from pathlib import Path

from . import claude_md, evidence


def load(project_root: str | Path) -> dict:
    """Config dict, or {} if CLAUDE.md has no '## Temper' block."""
    cfg, _err = claude_md.load_config(project_root)
    return cfg or {}


def load_strict(project_root: str | Path) -> tuple[dict | None, str | None]:
    """Like load() but returns the error string so callers can surface it."""
    return claude_md.load_config(project_root)


def _commands(cfg: dict) -> dict:
    return cfg.get("commands", {}) if isinstance(cfg, dict) else {}


def baseline_commands(cfg: dict) -> list[str]:
    return list(_commands(cfg).get("baseline", []))


def verify_commands(cfg: dict) -> list[str]:
    return list(_commands(cfg).get("verify", []))


def review_kind(cfg: dict) -> str:
    return _commands(cfg).get("review", "thermo-nuclear")


def _gate(cfg: dict) -> dict:
    return cfg.get("gate", {}) if isinstance(cfg, dict) else {}


def require_review(cfg: dict) -> bool:
    """Whether a task needs a signed verdict=pass review receipt (not just a green
    command receipt) before it can be marked passing. Default True — this is the
    enforcement that makes Temper's review load-bearing rather than advisory. Opt out
    with `[gate] require_review = false` in the ## Temper block."""
    return bool(_gate(cfg).get("require_review", True))


def guard_test_deletion(cfg: dict) -> bool:
    """Whether to block marking a task passing when its diff removes tests on net.
    Default True (deleting a failing test is the classic fake-green move)."""
    return bool(_gate(cfg).get("guard_test_deletion", True))


def test_globs(cfg: dict):
    """Globs that mark a file as a test, for the test-deletion guard. Default in
    test_evidence.DEFAULT_TEST_GLOBS; override with [gate] test_globs = [...]."""
    from . import test_evidence
    globs = _gate(cfg).get("test_globs")
    return tuple(globs) if globs else test_evidence.DEFAULT_TEST_GLOBS


def independent_review(cfg: dict) -> bool:
    """Whether the review receipt must name a reviewer distinct from the author (the
    two-key rule). Default True. Opt out with [gate] independent_review = false."""
    return bool(_gate(cfg).get("independent_review", True))


def plans_dir(project_root: str | Path) -> Path:
    return evidence.harness_dir(project_root) / "plans"
