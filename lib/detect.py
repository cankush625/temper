#!/usr/bin/env python3
"""Detect a repo's verify surface and print a `## Temper` config block proposal.

Heuristic and conservative: only emits commands whose targets/tools actually exist in
the repo. Backs /tp-init — a human reviews and trims before pasting into CLAUDE.md.

    python3 lib/detect.py <project_root>
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path


def _read(p: Path) -> str:
    try:
        return p.read_text()
    except OSError:
        return ""


def _make_targets(root: Path) -> set[str]:
    return set(re.findall(r"^([a-zA-Z0-9_.-]+):", _read(root / "Makefile"), re.M))


def _just_recipes(root: Path) -> set[str]:
    for name in ("Justfile", "justfile"):
        if (root / name).exists():
            return set(re.findall(r"^([a-zA-Z0-9_-]+)[ :]", _read(root / name), re.M))
    return set()


def detect(root: Path) -> tuple[str, str, list[str], list[str], list[str]]:
    """Return (name, kind, baseline, verify, notes)."""
    root = root.resolve()
    name, notes = root.name, []
    mk, jr = _make_targets(root), _just_recipes(root)
    is_py = any((root / f).exists() for f in
                ("pyproject.toml", "requirements.txt", "Pipfile", "poetry.lock", "uv.lock"))

    # AWS SAM
    if (root / "samconfig.toml").exists() or (root / "template.yaml").exists() or (root / "template.yml").exists():
        cmds = ["python3 -m compileall -q src",
                "sam validate --lint -t template.yaml"]
        notes.append("SAM: deploy/plan need cloud credentials — keep them out of verify.")
        return name, "sam", cmds, list(cmds), notes

    # Terraform via just
    if jr and list(root.glob("*.tf")):
        b = []
        if "fmt" in jr:
            b.append("just fmt")
        if "validate" in jr:
            b.append("just validate")
        if (root / ".pre-commit-config.yaml").exists():
            b.append("pre-commit run --all-files")
        if not b:
            b = ["terraform fmt -check -recursive"]
        notes.append("Terraform: a live plan/apply needs cloud credentials — escalation, not verify.")
        return name, "terraform", b, list(b), notes

    # Makefile-driven (common, non-org-specific target names only)
    if mk:
        cmds = ["make check"] if "check" in mk else \
               [f"make {t}" for t in ("lint", "format-check", "typecheck") if t in mk]
        cmds += [f"make {t}" for t in ("test", "tests", "unittest", "pytest") if t in mk]
        if cmds:
            return name, "python" if is_py else "make", cmds, list(cmds), notes
        notes.append("Makefile found but no recognized check/test targets — fill in by hand.")

    # Plain Python
    if is_py:
        cmds = ["python3 -m compileall -q ."]
        notes.append("No Makefile targets found; using a compile check. Add real tests if available.")
        return name, "python", cmds, list(cmds), notes

    notes.append("Could not auto-detect a verify surface — fill in [commands] by hand.")
    return name, "generic", [], [], notes


def _toml_array(xs: list[str]) -> str:
    if not xs:
        return "[]"
    return "[\n" + "".join(f"    {json.dumps(x)},\n" for x in xs) + "]"


def render(name: str, kind: str, baseline: list[str], verify: list[str]) -> str:
    return (
        f"[project]\n"
        f"name = {json.dumps(name)}\n"
        f"kind = {json.dumps(kind)}\n\n"
        f"[commands]\n"
        f"baseline = {_toml_array(baseline)}\n"
        f"verify = {_toml_array(verify)}\n"
        f'review = "thermo-nuclear"\n'
    )


def main() -> int:
    root = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(".")
    name, kind, baseline, verify, notes = detect(root)
    for n in notes:
        print(f"# note: {n}", file=sys.stderr)
    print("## Temper\n\n```toml")
    print(render(name, kind, baseline, verify).rstrip())
    print("```")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
