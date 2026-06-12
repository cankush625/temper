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


def plans_dir(project_root: str | Path) -> Path:
    return evidence.harness_dir(project_root) / "plans"
