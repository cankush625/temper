"""The JSON task list: an append-only contract with a one-way status rule.

Tasks may only move failing -> passing, never the reverse, and the list is
append-only (no deletion, no reordering). These rules are what stop an agent
from quietly editing the contract to make red look green.
"""

from __future__ import annotations

import json
from pathlib import Path

VALID_STATUSES = {"failing", "passing"}
REQUIRED_TASK_FIELDS = ("id", "title", "status")


def load(path: str | Path) -> dict:
    return json.loads(Path(path).read_text())


def loads(text: str) -> dict:
    return json.loads(text)


def tasks(plan: dict) -> list[dict]:
    return plan.get("tasks", []) if isinstance(plan, dict) else []


def validate(plan: dict) -> list[str]:
    errors: list[str] = []
    if not isinstance(plan, dict):
        return ["plan is not a JSON object"]
    seen: set[str] = set()
    for i, t in enumerate(tasks(plan)):
        if not isinstance(t, dict):
            errors.append(f"task[{i}] is not an object")
            continue
        for field in REQUIRED_TASK_FIELDS:
            if field not in t:
                errors.append(f"task[{i}] missing required field '{field}'")
        tid = t.get("id")
        if tid in seen:
            errors.append(f"duplicate task id '{tid}'")
        seen.add(tid)
        if t.get("status") not in VALID_STATUSES:
            errors.append(f"task '{tid}' has invalid status {t.get('status')!r}")
    return errors


def status_map(plan: dict) -> dict[str, str]:
    return {t.get("id"): t.get("status") for t in tasks(plan)}


def ids_in_order(plan: dict) -> list[str]:
    return [t.get("id") for t in tasks(plan)]


def newly_passing(old: dict | None, new: dict) -> list[dict]:
    """Tasks that are 'passing' in new but were not 'passing' in old."""
    old_status = status_map(old) if old else {}
    return [
        t for t in tasks(new)
        if t.get("status") == "passing" and old_status.get(t.get("id")) != "passing"
    ]


def append_only_violations(old: dict | None, new: dict) -> list[str]:
    """Detect deletions, reordering, and passing->failing reversals."""
    if not old:
        return []
    violations: list[str] = []
    old_ids = ids_in_order(old)
    new_ids = ids_in_order(new)

    removed = [i for i in old_ids if i not in new_ids]
    if removed:
        violations.append(f"tasks removed (append-only): {removed}")

    # Reorder check on the tasks that survive in both.
    common_old = [i for i in old_ids if i in new_ids]
    common_new = [i for i in new_ids if i in old_ids]
    if common_old != common_new:
        violations.append("existing tasks reordered (append-only)")

    old_status = status_map(old)
    new_status = status_map(new)
    for tid, st in old_status.items():
        if st == "passing" and new_status.get(tid) == "failing":
            violations.append(f"task '{tid}' reverted passing -> failing")
    return violations
