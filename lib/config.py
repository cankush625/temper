"""Per-project config: maps the harness's abstract verify surface to the real
commands a given repo uses (terraform/just for forge, make for the Python repos).

The engine never hardcodes pytest or terraform — it reads them from here.
"""

from __future__ import annotations

import tomllib
from pathlib import Path

from . import evidence

CONFIG_FILENAME = "config.toml"


def config_path(project_root: str | Path) -> Path:
    return evidence.harness_dir(project_root) / CONFIG_FILENAME


def load(project_root: str | Path) -> dict:
    path = config_path(project_root)
    if not path.exists():
        return {}
    with open(path, "rb") as f:
        return tomllib.load(f)


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
