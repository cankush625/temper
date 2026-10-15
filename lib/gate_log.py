"""Gate log: a short, append-only record of every time a gate blocked.

A block is printed to the agent once and then gone. The session-start hook reads this log so
the next session opens knowing what was refused last time and why, instead of rediscovering it.
Bounded: only the newest MAX_ENTRIES are kept.
"""

from __future__ import annotations

import datetime as dt
import json
from pathlib import Path

from . import evidence

FILENAME = "gate_log.jsonl"
MAX_ENTRIES = 200


def log_path(project_root: str | Path) -> Path:
    """
    Where the gate log lives for a project.

    Example:
        >>> log_path("/repo").as_posix()
        '/repo/.temper/gate_log.jsonl'
    """

    return evidence.harness_dir(project_root) / FILENAME


def append(project_root: str | Path, gate: str, reasons: list[str]) -> None:
    """
    Record one block by `gate` with its reasons, trimming the log to MAX_ENTRIES.

    A repeat of the newest entry (same gate, same reasons) is not appended again: a Stop hook
    that keeps blocking the same claims would otherwise fill the log with one message.

    Example:
        >>> append(root, "evidence_gate", ["task 'T1' has no receipt"])  # doctest: +SKIP
    """

    path = log_path(project_root)
    if not path.parent.is_dir():
        return
    entry = {"at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
             "gate": gate, "reasons": reasons}
    lines = path.read_text().splitlines() if path.exists() else []
    if lines:
        try:
            last = json.loads(lines[-1])
        except json.JSONDecodeError:
            last = {}
        if last.get("gate") == gate and last.get("reasons") == reasons:
            return
    lines.append(json.dumps(entry))
    path.write_text("\n".join(lines[-MAX_ENTRIES:]) + "\n")


def recent(project_root: str | Path, n: int) -> list[dict]:
    """
    The newest `n` entries, oldest first. Unreadable lines are skipped.

    Example:
        >>> recent(root, 3)  # doctest: +SKIP
        [{'at': '2026-10-15T10:00:00+00:00', 'gate': 'session_integrity', 'reasons': [...]}]
    """

    path = log_path(project_root)
    if n <= 0 or not path.exists():
        return []
    out = []
    for line in path.read_text().splitlines()[-n:]:
        try:
            out.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return out
