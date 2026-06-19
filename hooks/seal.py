#!/usr/bin/env python3
"""seal.py — post-commit sealer. Freezes a proven-and-committed claim into a receipt.

Temper's ledger (`.temper/`) is intentionally local and shared across every branch in
the working tree (`temper init` excludes it from git). So "is this passing task still
backed?" cannot be answered by which branch holds the file — there is only one ledger.
Instead, when a commit lands, this seals every passing-but-unsealed task to that commit:
the task was already required to hold fresh command + review receipts when it was flipped
to passing (`evidence_gate` enforces that at flip time), and committing settles it. The
standing audit (`session_integrity`) then treats a sealed task whose commit still exists
as a historical fact rather than re-validating its receipt against the current — possibly
another branch's — tree.

Run by the git post-commit hook (`scripts/git-hooks/post-commit`). Also runnable by hand
to seal already-committed work:  python3 hooks/seal.py [project_root]

Idempotent: never re-seals an already-sealed task, never un-seals, never touches a
`failing` task. Fails OPEN (exit 0) — a sealer error must never disrupt the user's commit.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from lib import config, evidence, plan_schema  # noqa: E402


def seal(root: Path) -> list[str]:
    """Seal every passing-but-unsealed task to the current HEAD. Returns sealed ids."""
    plans_dir = config.plans_dir(root)
    if not plans_dir.is_dir():
        return []
    head = evidence.git_state(root).get("sha")
    if not head or head == "NO_HEAD":
        return []  # nothing to seal to yet
    key = evidence.load_or_create_key(root)

    sealed_ids: list[str] = []
    for plan_file in sorted(plans_dir.glob("*.json")):
        try:
            plan = plan_schema.load(plan_file)
        except (OSError, json.JSONDecodeError):
            continue
        changed = False
        for task in plan_schema.tasks(plan):
            tid = task.get("id")
            if task.get("status") == "passing" and not plan_schema.sealed_commit(task):
                task["sealed"] = {"commit": head, "signature": evidence.sign_seal(tid, head, key)}
                sealed_ids.append(tid)
                changed = True
        if changed:
            plan_file.write_text(json.dumps(plan, indent=2) + "\n")
    return sealed_ids


def main() -> int:
    root = evidence.find_project_root(sys.argv[1] if len(sys.argv) > 1 else None)
    ids = seal(root)
    if ids:
        print(f"[temper] sealed {len(ids)} committed task(s): {', '.join(str(i) for i in ids)}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except SystemExit:
        raise
    except Exception as exc:  # fail OPEN: never disrupt a commit
        print(f"[seal] internal error, failing open: {exc}", file=sys.stderr)
        raise SystemExit(0)
