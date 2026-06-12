#!/usr/bin/env python3
"""capture.py — run a command for real and write a signed evidence receipt.

This is the ONLY sanctioned way to produce evidence that a task passes. It runs
the command, streams its output, records the true exit code, pins the current
code state, signs the record, and exits with the command's own exit code (so the
agent cannot pretend a failing command passed).

Usage:
    capture.py --task T1 --claim "tests pass" -- make test
    capture.py --task T1 --kind baseline -- make check

Anything after `--` is the command, run as-is (no shell) from --project (default:
the nearest ancestor dir containing .temper/).
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from lib import evidence  # noqa: E402

TAIL_CHARS = 4000


def _now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat()


def _slug(parts: list[str]) -> str:
    base = "-".join(parts)[:40]
    return "".join(c if c.isalnum() or c in "-_" else "_" for c in base) or "cmd"


def main() -> int:
    ap = argparse.ArgumentParser(description="Record a signed evidence receipt for a command.")
    ap.add_argument("--task", required=True, help="task id this evidence is for (e.g. T1)")
    ap.add_argument("--claim", default="", help="human-readable claim being verified")
    ap.add_argument("--kind", default="verify", choices=["baseline", "verify", "review"],
                    help="what stage this evidence belongs to")
    ap.add_argument("--plan", default="", help="optional plan slug for bookkeeping")
    ap.add_argument("--project", default="", help="project root (default: nearest .temper ancestor)")
    ap.add_argument("command", nargs=argparse.REMAINDER,
                    help="the command to run, after a literal --")
    args = ap.parse_args()

    cmd = args.command
    if cmd and cmd[0] == "--":
        cmd = cmd[1:]
    if not cmd:
        ap.error("no command given; put it after a literal --")

    root = Path(args.project).resolve() if args.project else evidence.find_project_root()
    state_before = evidence.git_state(root)

    started = _now()
    print(f"[capture] task={args.task} kind={args.kind} :: {' '.join(cmd)}", file=sys.stderr)
    proc = subprocess.run(cmd, cwd=root, capture_output=True, text=True)
    finished = _now()

    # Stream the real output through so the agent and user see it.
    sys.stdout.write(proc.stdout)
    sys.stderr.write(proc.stderr)

    state_after = evidence.git_state(root)
    if state_after != state_before:
        print("[capture] WARNING: code state changed during the run; recording post-run state.",
              file=sys.stderr)

    record = {
        "schema_version": evidence.SCHEMA_VERSION,
        "task_id": args.task,
        "plan": args.plan,
        "kind": args.kind,
        "claim": args.claim,
        "command": cmd,
        "exit_code": proc.returncode,
        "started_at": started,
        "finished_at": finished,
        "cwd": str(root),
        "git_state": state_after,
        "stdout_tail": proc.stdout[-TAIL_CHARS:],
        "stderr_tail": proc.stderr[-TAIL_CHARS:],
        "stdout_sha256": hashlib.sha256(proc.stdout.encode("utf-8")).hexdigest(),
    }
    key = evidence.load_or_create_key(root)
    record["signature"] = evidence.sign(record, key)

    out_dir = evidence.evidence_dir(root, args.task)
    out_dir.mkdir(parents=True, exist_ok=True)
    ts = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out_path = out_dir / f"{ts}-{_slug(cmd)}.json"
    out_path.write_text(json.dumps(record, indent=2))

    verdict = "PASS" if proc.returncode == 0 else f"FAIL(exit {proc.returncode})"
    rel = os.path.relpath(out_path, root)
    print(f"[capture] {verdict} -> {rel}", file=sys.stderr)
    if proc.returncode != 0:
        print("[capture] This receipt records a FAILURE; it will NOT let you mark the task passing.",
              file=sys.stderr)
    return proc.returncode


if __name__ == "__main__":
    raise SystemExit(main())
