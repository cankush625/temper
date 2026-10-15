#!/usr/bin/env python3
"""session_start.py — SessionStart hook. Open every session knowing the ledger's state.

Temper's gates act at plan edits (PreToolUse) and at Stop. Without this hook a new session
starts blind: it doesn't know which tasks are open, which passing claims have gone stale since
the code changed, or what a gate refused last time. This hook adds a short context block with:

  - each plan's progress and its next open task (plans are ordered by priority);
  - passing claims the Stop hook would reject right now (stale or missing receipts);
  - the most recent gate blocks, one line each;
  - the skills Temper has learned (hooks/learn.py), grouped by category, plus a one-line account
    of the last learning run — what landed and what the promoter rejected and why.

Before the learned-skill index is built, the lifecycle pass (lib/lifecycle.py) archives learned
skills that have stopped earning their place, so the index shows only what survives.

Nothing is added when the project has no .temper/, or has neither plans nor learned skills. The block is capped at
MAX_LINES. Fails OPEN: on internal error it prints a one-line note and exits 0.

Wired by `temper init` into .claude/settings.local.json under hooks.SessionStart.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

HOOKS_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(HOOKS_DIR.parent))
sys.path.insert(0, str(HOOKS_DIR))
import session_integrity  # noqa: E402
from lib import config, evidence, gate_log, lifecycle, plan_schema, skill_store  # noqa: E402

MAX_LINES = 60
RECENT_BLOCKS = 3
REASON_CHARS = 160


def _short(text: str, limit: int = REASON_CHARS) -> str:
    """
    Collapse whitespace and cut `text` to `limit` characters.

    Example:
        >>> _short("a  b\\n c", 4)
        'a b…'
    """

    flat = " ".join(str(text).split())
    return flat if len(flat) <= limit else flat[: limit - 1] + "…"


def _plan_lines(root: Path) -> list[str]:
    """
    One line per plan: passing/total and the next open task.

    Example:
        >>> _plan_lines(root)  # doctest: +SKIP
        ['- demo: 1/3 passing; next: T2 "Add the parser"']
    """

    lines = []
    plans_dir = config.plans_dir(root)
    for plan_file in sorted(plans_dir.glob("*.json")) if plans_dir.is_dir() else []:
        try:
            plan = plan_schema.load(plan_file)
        except (OSError, json.JSONDecodeError):
            lines.append(f"- {plan_file.stem}: unreadable / invalid JSON")
            continue
        tasks = plan_schema.tasks(plan)
        done = sum(1 for t in tasks if t.get("status") == "passing")
        nxt = next((t for t in tasks if t.get("status") != "passing"), None)
        tail = f'next: {nxt.get("id")} "{_short(nxt.get("title", ""), 80)}"' if nxt else "all passing"
        lines.append(f"- {plan_file.stem}: {done}/{len(tasks)} passing; {tail}")
    return lines


def _ledger_lines(root: Path) -> list[str]:
    """
    The plan / stale-claim / gate-block section, or [] when there are no plans.

    Example:
        >>> _ledger_lines(root)  # doctest: +SKIP
        ['Temper ledger (.temper/):', 'Plans:', '- demo: 1/3 passing; next: T2 "Add the parser"']
    """

    plans = _plan_lines(root)
    if not plans:
        return []
    out = ["Temper ledger (.temper/):", "Plans:", *plans]
    problems = session_integrity._audit(root)
    if problems:
        out.append("Passing claims the Stop hook would reject now (re-verify or revert to failing):")
        out.extend(f"- {_short(p)}" for p in problems)
    blocks = gate_log.recent(root, RECENT_BLOCKS)
    if blocks:
        out.append("Recent gate blocks (newest last):")
        for b in blocks:
            reasons = b.get("reasons") or []
            more = f" (+{len(reasons) - 1} more)" if len(reasons) > 1 else ""
            first = _short(reasons[0]) if reasons else "no reason recorded"
            out.append(f"- {b.get('at', '?')} {b.get('gate', '?')}: {first}{more}")
    return out


def _last_run_line(root: Path) -> str:
    """
    One line on the most recent learning run, or "" when there has been none.

    Example:
        >>> _last_run_line(root)  # doctest: +SKIP
        'Last learning run (2026-10-15T10:15:00+00:00, reflect): landed create tl-x; rejected: tl-y (...)'
    """

    path = skill_store.state_dir("project", root) / "last_run.json"
    try:
        run = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError):
        return ""
    landed = ", ".join(f"{x.get('action')} {x.get('name')}" for x in run.get("landed", [])) or "nothing"
    parts = [f"Last learning run ({run.get('at', '?')}, {run.get('kind', '?')}): landed {landed}"]
    rejected = run.get("rejected", [])
    if rejected:
        parts.append("rejected: " + "; ".join(
            f"{x.get('name') or '?'} ({_short(x.get('reason', ''), 80)})" for x in rejected[:3]))
    if run.get("error"):
        parts.append(f"error: {_short(run['error'], 80)}")
    return " · ".join(parts)


def _learned_lines(root: Path) -> list[str]:
    """
    The learned-skill section: lifecycle archives, the grouped index, and the last run.

    Example:
        >>> _learned_lines(root)  # doctest: +SKIP
        ['Learned skills (Temper; load with the Skill tool when the trigger fits):', 'ops:', ...]
    """

    settings = config.learn(config.load(root))
    if not settings["enabled"]:
        return []
    archived = lifecycle.run(root, settings)
    layers = skill_store.LAYERS if settings["global"] else ("project",)
    index = skill_store.index_lines(skill_store.managed(root, layers))
    out = []
    if index:
        out.append("Learned skills (Temper; load with the Skill tool when the trigger fits):")
        out.extend(index)
    if archived:
        out.append("Archived by the lifecycle this session: " + ", ".join(
            f"{a['name']} ({a['reason']})" for a in archived))
    last = _last_run_line(root)
    if last:
        out.append(last)
    return out


def build_context(root: Path) -> str:
    """
    The context block for a session in `root`, or "" when there is nothing to say.

    Example:
        >>> print(build_context(root))  # doctest: +SKIP
        Temper ledger (.temper/):
        Plans:
        - demo: 1/3 passing; next: T2 "Add the parser"
    """

    if not evidence.harness_dir(root).is_dir():
        return ""
    out = _ledger_lines(root)
    try:
        out.extend(_learned_lines(root))
    except Exception as exc:  # the learned index must never cost the ledger summary
        out.append(f"(learned-skill index unavailable: {_short(str(exc), 80)})")
    if len(out) > MAX_LINES:
        out = out[: MAX_LINES - 1] + [f"… {len(out) - MAX_LINES + 1} more lines; see .temper/"]
    return "\n".join(out)


def main() -> int:
    raw = sys.stdin.read()
    data = json.loads(raw) if raw.strip() else {}
    root = evidence.find_project_root(data.get("cwd"))
    context = build_context(root)
    if context:
        print(json.dumps({"hookSpecificOutput": {"hookEventName": "SessionStart",
                                                 "additionalContext": context}}))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except SystemExit:
        raise
    except Exception as exc:  # fail OPEN: a broken ledger must never break the session
        print(f"[session_start] internal error, skipping ledger summary: {exc}", file=sys.stderr)
        raise SystemExit(0)
