"""Where learned skills live, and the bookkeeping that keeps them Temper's own.

Two layers, both plain Claude Code skill folders:

  project  <repo>/.claude/skills/tl-<name>/     (git-excluded by `temper init`)
  global   ~/.claude/skills/tl-<name>/          (loads in every project)

A folder is *managed* only when it holds the marker `.temper-learned.json`, which only the
promoter writes. Everything else in a skills directory — skills you wrote or installed — is
invisible to the learning loop. Each managed skill carries:

  SKILL.md                     the skill (native format)
  .temper-learned.json         marker + lifecycle counters (created at, uses, patches)
  .ledger.jsonl                append-only: why it was created or changed, with evidence
  references/evidence-*.md     the verbatim transcript slice behind each ledger entry

Retiring a skill moves its whole folder to the layer's archive (outside the skills tree, so
it is out of recall) — never a delete. Moving it back revives it with its history.
"""

from __future__ import annotations

import datetime as dt
import json
import os
import re
import shutil
import tarfile
from dataclasses import dataclass
from pathlib import Path

from . import evidence

PREFIX = "tl-"
MARKER = ".temper-learned.json"
LEDGER = ".ledger.jsonl"
SNAPSHOTS_KEPT = 5
LAYERS = ("project", "global")


def now() -> str:
    """
    The current UTC time, to the second, ISO-8601.

    Example:
        >>> len(now()) >= 19
        True
    """

    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")


def global_home() -> Path:
    """
    The user-wide Claude directory: $TEMPER_LEARN_HOME if set (tests), else ~/.claude.

    Example:
        >>> global_home().name  # doctest: +SKIP
        '.claude'
    """

    return Path(os.environ.get("TEMPER_LEARN_HOME") or Path.home() / ".claude")


def skills_dir(layer: str, project_root: str | Path) -> Path:
    """
    The skills directory for a layer.

    Example:
        >>> skills_dir("project", "/repo").as_posix()
        '/repo/.claude/skills'
    """

    return (Path(project_root) / ".claude" if layer == "project" else global_home()) / "skills"


def state_dir(layer: str, project_root: str | Path) -> Path:
    """
    Where a layer keeps its learning state (counters, runs, archive, snapshots).

    Example:
        >>> state_dir("project", "/repo").as_posix()
        '/repo/.temper/learn'
    """

    if layer == "project":
        return evidence.harness_dir(project_root) / "learn"
    return global_home() / "temper-learn"


def frontmatter(body: str) -> tuple[dict[str, str], str] | None:
    """
    Split a SKILL.md into (simple key: value frontmatter, rest), or None when it has none.

    Example:
        >>> frontmatter("---\\nname: tl-x\\ndescription: Use when X.\\n---\\nDo Y.\\n")
        ({'name': 'tl-x', 'description': 'Use when X.'}, 'Do Y.\\n')
    """

    text = body.replace("\r\n", "\n")
    match = re.match(r"---\n(.*?)\n---\n?(.*)", text, re.S)
    if not match:
        return None
    fields = {}
    for line in match.group(1).splitlines():
        if ":" in line and not line.startswith((" ", "\t", "#")):
            key, _, value = line.partition(":")
            fields[key.strip()] = value.strip().strip("\"'")
    return fields, match.group(2)


def set_name(body: str, name: str) -> str:
    """
    Force the frontmatter `name:` to `name`, adding it when missing.

    Example:
        >>> set_name("---\\nname: x\\ndescription: d\\n---\\nb", "tl-x")
        '---\\nname: tl-x\\ndescription: d\\n---\\nb'
    """

    text = body.replace("\r\n", "\n")
    head, sep, rest = text[4:].partition("\n---")
    lines = [ln for ln in head.split("\n") if not ln.startswith("name:")]
    return "---\n" + "\n".join([f"name: {name}", *lines]) + sep + rest


@dataclass
class Skill:
    """
    One managed skill as the loop sees it.

    Example:
        >>> Skill("tl-x", "project", Path("/r/.claude/skills/tl-x"), {}, "Use when X.", "ops").name
        'tl-x'
    """

    name: str
    layer: str
    path: Path
    meta: dict
    description: str
    category: str

    @property
    def body(self) -> str:
        return (self.path / "SKILL.md").read_text()


def _read_json(path: Path) -> dict:
    try:
        data = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def write_json(path: Path, data: dict) -> None:
    """
    Write JSON atomically: to a temp file in the same directory, then rename over the target.

    Example:
        >>> write_json(Path("/tmp/state.json"), {"requests": 3})  # doctest: +SKIP
    """

    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.tmp-{os.getpid()}")
    tmp.write_text(json.dumps(data, indent=2) + "\n")
    os.replace(tmp, path)


def write_text(path: Path, text: str) -> None:
    """
    Write text atomically (temp file + rename), creating parent directories.

    Example:
        >>> write_text(Path("/tmp/x/SKILL.md"), "---\\n...")  # doctest: +SKIP
    """

    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.tmp-{os.getpid()}")
    tmp.write_text(text)
    os.replace(tmp, path)


def is_managed(path: Path) -> bool:
    """
    Whether a skill folder is one the promoter created (holds the marker).

    Example:
        >>> is_managed(Path("/nonexistent"))
        False
    """

    return (path / MARKER).is_file()


def managed(project_root: str | Path, layers: tuple[str, ...] = LAYERS) -> list[Skill]:
    """
    Every live managed skill in the given layers, sorted by layer then name.

    Example:
        >>> [s.name for s in managed("/repo")]  # doctest: +SKIP
        ['tl-deploy-checks', 'tl-terraform-plans']
    """

    out = []
    for layer in layers:
        base = skills_dir(layer, project_root)
        if not base.is_dir():
            continue
        for path in sorted(base.glob(f"{PREFIX}*")):
            if not (path.is_dir() and is_managed(path) and (path / "SKILL.md").is_file()):
                continue
            parsed = frontmatter((path / "SKILL.md").read_text()) or ({}, "")
            out.append(Skill(path.name, layer, path, _read_json(path / MARKER),
                             parsed[0].get("description", ""), parsed[0].get("category", "general")))
    return out


def find(project_root: str | Path, name: str, layers: tuple[str, ...] = LAYERS) -> Skill | None:
    """
    The live managed skill called `name` (first match, project before global), if any.

    Example:
        >>> find("/repo", "tl-missing") is None  # doctest: +SKIP
        True
    """

    return next((s for s in managed(project_root, layers) if s.name == name), None)


def index_lines(skills: list[Skill], desc_chars: int = 90) -> list[str]:
    """
    The skill index: grouped by category, one `- name [layer]: description` line each.

    Example:
        >>> s = Skill("tl-x", "project", Path("p"), {}, "Use when X.", "ops")
        >>> index_lines([s])
        ['ops:', '  - tl-x [project]: Use when X.']
    """

    lines = []
    by_cat: dict[str, list[Skill]] = {}
    for s in skills:
        by_cat.setdefault(s.category or "general", []).append(s)
    for cat in sorted(by_cat):
        lines.append(f"{cat}:")
        for s in by_cat[cat]:
            desc = s.description if len(s.description) <= desc_chars else s.description[: desc_chars - 1] + "…"
            lines.append(f"  - {s.name} [{s.layer}]: {desc}")
    return lines


def append_ledger(path: Path, entry: dict) -> None:
    """
    Append one entry to a skill's ledger.

    Example:
        >>> append_ledger(Path("skill"), {"action": "create", "reason": "..."})  # doctest: +SKIP
    """

    with open(path / LEDGER, "a") as f:
        f.write(json.dumps({"at": now(), **entry}) + "\n")


def archive(skill: Skill, project_root: str | Path, entry: dict) -> Path:
    """
    Move a managed skill out of recall into its layer's archive, logging why. Returns the new path.

    Example:
        >>> archive(skill, "/repo", {"action": "archive", "reason": "unused"})  # doctest: +SKIP
        PosixPath('/repo/.temper/learn/archive/tl-x-20261015T101500Z')
    """

    append_ledger(skill.path, entry)
    dest_dir = state_dir(skill.layer, project_root) / "archive"
    dest_dir.mkdir(parents=True, exist_ok=True)
    stamp = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    dest = dest_dir / f"{skill.name}-{stamp}"
    shutil.move(str(skill.path), dest)
    return dest


def snapshot(layer: str, project_root: str | Path) -> Path | None:
    """
    Tar the layer's managed skills before a curator run, keeping the newest SNAPSHOTS_KEPT.

    Example:
        >>> snapshot("project", "/repo")  # doctest: +SKIP
        PosixPath('/repo/.temper/learn/snapshots/20261015T101500Z.tar.gz')
    """

    skills = managed(project_root, (layer,))
    if not skills:
        return None
    snap_dir = state_dir(layer, project_root) / "snapshots"
    snap_dir.mkdir(parents=True, exist_ok=True)
    out = snap_dir / f"{dt.datetime.now(dt.timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')}.tar.gz"
    with tarfile.open(out, "w:gz") as tar:
        for s in skills:
            tar.add(s.path, arcname=s.name)
    for old in sorted(snap_dir.glob("*.tar.gz"))[:-SNAPSHOTS_KEPT]:
        old.unlink()
    return out
