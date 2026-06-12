#!/usr/bin/env python3
"""session_integrity.py — Stop hook. The backstop against the end-of-session bluff.

When the agent tries to end its turn, this re-audits every plan: any task marked
"passing" must have a valid, current, exit-0 receipt. If not, it blocks the stop
(exit 2) and names the offending tasks, so the agent must either capture real
evidence or revert the status before it can declare itself done.

Fails OPEN on internal error (exit 0, loud warning) so a hook bug never traps the
user in an unstoppable session.

Wire in a project's .claude/settings.json under hooks.Stop.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from lib import config, evidence, plan_schema  # noqa: E402


def _audit(root: Path) -> list[str]:
    problems: list[str] = []
    plans_dir = config.plans_dir(root)
    if not plans_dir.is_dir():
        return problems
    for plan_file in sorted(plans_dir.glob("*.json")):
        try:
            plan = plan_schema.load(plan_file)
        except (OSError, json.JSONDecodeError):
            problems.append(f"{plan_file.name}: unreadable / invalid JSON")
            continue
        for task in plan_schema.tasks(plan):
            if task.get("status") != "passing":
                continue
            tid = task.get("id")
            if not evidence.valid_evidence_for_task(root, tid):
                problems.append(
                    f"{plan_file.name}: task '{tid}' is marked passing but has no valid "
                    f"exit-0 receipt for the current code state."
                )
    return problems


def main() -> int:
    raw = sys.stdin.read()
    data = json.loads(raw) if raw.strip() else {}
    root = evidence.find_project_root(data.get("cwd"))

    problems = _audit(root)
    if not problems:
        return 0

    msg = (
        "ANTI-BLUFF STOP HOOK: cannot end the session — the task list claims work that "
        "isn't backed by evidence:\n\n"
        + "\n".join(f"  - {p}" for p in problems)
        + "\n\nFix before stopping: either run\n"
        "  temper capture --task <ID> --claim \"...\" -- <verify command>\n"
        "until it exits 0 on the current code, or set the task's status back to \"failing\"."
    )
    print(msg, file=sys.stderr)
    return 2


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except SystemExit:
        raise
    except Exception as exc:  # fail OPEN: never trap the user
        print(f"[session_integrity] internal error, failing open: {exc}", file=sys.stderr)
        raise SystemExit(0)
