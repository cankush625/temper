"""Read Temper's per-project config from CLAUDE.md.

Convention: a single fenced ```toml block under a `## Temper` heading is the human +
machine source of truth for verify commands. This keeps one config (no separate file)
that a person reading CLAUDE.md sees too.

    ## Temper
    ```toml
    [project]
    name = "forge"
    kind = "terraform"

    [commands]
    baseline = ["just fmt", "just validate dev"]
    verify   = ["just validate dev"]
    review   = "thermo-nuclear"
    ```
"""

from __future__ import annotations

import re
import tomllib
from pathlib import Path

SECTION = "Temper"


def claude_md_path(project_root: str | Path) -> Path:
    return Path(project_root) / "CLAUDE.md"


def extract_block(text: str) -> str | None:
    """Return the toml inside the fenced block under '## Temper', or None."""
    lines = text.splitlines()
    start = None
    for i, ln in enumerate(lines):
        if re.match(rf"^##\s+{re.escape(SECTION)}\b", ln.strip()):
            start = i
            break
    if start is None:
        return None
    # Region runs until the next '## ' heading (or EOF).
    region = []
    for ln in lines[start + 1:]:
        if re.match(r"^##\s+\S", ln):
            break
        region.append(ln)
    m = re.search(r"```toml\s*\n(.*?)\n```", "\n".join(region), re.DOTALL)
    return m.group(1) if m else None


def load_config(project_root: str | Path) -> tuple[dict | None, str | None]:
    """Return (config, error). On success error is None."""
    path = claude_md_path(project_root)
    if not path.exists():
        return None, "no CLAUDE.md found at project root"
    block = extract_block(path.read_text())
    if block is None:
        return None, "no '## Temper' toml block in CLAUDE.md — run /tp-init"
    try:
        return tomllib.loads(block), None
    except tomllib.TOMLDecodeError as exc:
        return None, f"invalid toml in the '## Temper' block: {exc}"


def render_block(config_toml: str) -> str:
    """Wrap raw toml as the CLAUDE.md section (for /tp-init to write)."""
    return f"## Temper\n\n```toml\n{config_toml.strip()}\n```\n"
