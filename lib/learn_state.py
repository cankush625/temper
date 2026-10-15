"""Per-layer learning state, read and written under a file lock.

  <state_dir>/state.json   {"requests": N, "sessions": {<session_id>: {...}}}

`requests` counts user prompts that reached the layer (a project's sessions for the project
layer; every project's sessions for the global layer) — the lifecycle's clock, so a skill ages
with use of the tool, not with wall time. `sessions` holds, per main session, where the Stop
hook last read the transcript and how many tool calls have passed since the last reflection
and the last curator run.

Hooks for concurrent sessions can fire at the same moment, so every read-modify-write goes
through `locked()`.
"""

from __future__ import annotations

import fcntl
import json
from contextlib import contextmanager
from pathlib import Path

from . import skill_store

SESSION_DEFAULTS = {"offset": 0, "window_start": 0, "calls": 0, "curate_calls": 0}
MAX_SESSIONS = 50


@contextmanager
def locked(layer: str, project_root: str | Path):
    """
    Yield the layer's state dict under an exclusive lock; it is saved when the block exits.

    Example:
        >>> with locked("project", root) as st:  # doctest: +SKIP
        ...     st["requests"] += 1
    """

    base = skill_store.state_dir(layer, project_root)
    base.mkdir(parents=True, exist_ok=True)
    path = base / "state.json"
    with open(base / ".state.lock", "w") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        try:
            state = json.loads(path.read_text()) if path.exists() else {}
        except json.JSONDecodeError:
            state = {}
        if not isinstance(state, dict):
            state = {}
        state.setdefault("requests", 0)
        state.setdefault("sessions", {})
        yield state
        sessions = state["sessions"]
        if len(sessions) > MAX_SESSIONS:  # keep the most recently touched sessions only
            keep = sorted(sessions, key=lambda k: sessions[k].get("touched", ""))[-MAX_SESSIONS:]
            state["sessions"] = {k: sessions[k] for k in keep}
        skill_store.write_json(path, state)


def requests(layer: str, project_root: str | Path) -> int:
    """
    The layer's request count (0 when it has no state yet).

    Example:
        >>> requests("project", "/repo")  # doctest: +SKIP
        42
    """

    path = skill_store.state_dir(layer, project_root) / "state.json"
    try:
        return int(json.loads(path.read_text()).get("requests", 0))
    except (OSError, ValueError, AttributeError, TypeError):
        return 0


def session(state: dict, session_id: str) -> dict:
    """
    The per-session entry in `state`, created with defaults when missing.

    Example:
        >>> session({"sessions": {}}, "abc")["calls"]
        0
    """

    entry = state["sessions"].setdefault(session_id, {})
    for key, value in SESSION_DEFAULTS.items():
        entry.setdefault(key, value)
    return entry
