#!/usr/bin/env python3
"""evidence_gate.py — PreToolUse hook. The hard floor against bluffing the task list.

Fires on Edit/Write/MultiEdit to a .harness/plans/*.json file. It reconstructs the
content the tool *would* write, and blocks (exit 2) if that edit would:
  - flip any task to "passing" without a valid, current, exit-0 evidence receipt, or
  - violate append-only rules (delete/reorder tasks, or revert passing -> failing).

Anything else is allowed (exit 0). On internal error it fails OPEN (exit 0, loud
warning) so a bug here can never brick the user's session — the Stop hook is the
backstop.

Wire in a project's .claude/settings.json under hooks.PreToolUse for Edit|Write|MultiEdit.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from lib import evidence, plan_schema  # noqa: E402


def _resulting_content(tool_name: str, tool_input: dict, current_text: str | None) -> str | None:
    if tool_name == "Write":
        return tool_input.get("content")
    if tool_name == "Edit":
        if current_text is None:
            return None
        old, new = tool_input.get("old_string", ""), tool_input.get("new_string", "")
        if tool_input.get("replace_all"):
            return current_text.replace(old, new)
        return current_text.replace(old, new, 1)
    if tool_name == "MultiEdit":
        if current_text is None:
            return None
        text = current_text
        for e in tool_input.get("edits", []):
            old, new = e.get("old_string", ""), e.get("new_string", "")
            text = text.replace(old, new) if e.get("replace_all") else text.replace(old, new, 1)
        return text
    return None


def _is_plan_file(path: Path, root: Path) -> bool:
    plans = (evidence.harness_dir(root) / "plans").resolve()
    try:
        path.resolve().relative_to(plans)
    except ValueError:
        return False
    return path.suffix == ".json"


def _block(reasons: list[str]) -> int:
    msg = "ANTI-BLUFF GATE BLOCKED THIS EDIT.\n\n" + "\n".join(f"  - {r}" for r in reasons)
    msg += (
        "\n\nTo mark a task passing you must first produce a real receipt:\n"
        "  python3 <harness>/hooks/capture.py --task <ID> --claim \"...\" -- <verify command>\n"
        "and the command must exit 0 on the CURRENT code state. Stale receipts (code changed\n"
        "since capture) do not count. Or revert the status back to \"failing\"."
    )
    print(msg, file=sys.stderr)
    return 2


def main() -> int:
    raw = sys.stdin.read()
    data = json.loads(raw) if raw.strip() else {}
    tool_name = data.get("tool_name", "")
    tool_input = data.get("tool_input", {}) or {}
    file_path = tool_input.get("file_path")
    if not file_path or tool_name not in ("Write", "Edit", "MultiEdit"):
        return 0

    root = evidence.find_project_root(data.get("cwd"))
    path = Path(file_path)
    if not _is_plan_file(path, root):
        return 0

    current_text = path.read_text() if path.exists() else None
    new_text = _resulting_content(tool_name, tool_input, current_text)
    if new_text is None:
        return 0

    try:
        new_plan = plan_schema.loads(new_text)
    except json.JSONDecodeError:
        return 0  # not our concern; malformed JSON isn't a passing-bluff
    old_plan = None
    if current_text:
        try:
            old_plan = plan_schema.loads(current_text)
        except json.JSONDecodeError:
            old_plan = None

    reasons: list[str] = []
    reasons.extend(plan_schema.append_only_violations(old_plan, new_plan))

    for task in plan_schema.newly_passing(old_plan, new_plan):
        tid = task.get("id")
        if not evidence.valid_evidence_for_task(root, tid):
            reasons.append(
                f"task '{tid}' set to passing but has no valid exit-0 receipt for the "
                f"current code state (looked in .harness/evidence/{tid}/)."
            )

    if reasons:
        return _block(reasons)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except SystemExit:
        raise
    except Exception as exc:  # fail OPEN: never brick the session
        print(f"[evidence_gate] internal error, failing open: {exc}", file=sys.stderr)
        raise SystemExit(0)
