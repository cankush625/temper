#!/usr/bin/env python3
"""review_capture.py — sign a code-review verdict into a tamper-evident receipt.

This is the ONLY sanctioned way to record that a task passed review. A verdict on
its own is just a model's say-so; routed through here it becomes a signed receipt
pinned to the exact code state it reviewed (git sha + working-tree digest). The gate
then requires a verdict=pass review receipt — for the CURRENT tree — before a task can
be marked passing, alongside the green-command receipt. If the code changes after the
review, the receipt goes stale and the review must be re-run, exactly like a test.

Read the verdict as JSON from --in <file> or stdin:
    {
      "task": "T1",
      "verdict": "pass" | "block",
      "reviewer": "<agent/context id>",     # optional; for the two-key independence rule
      "summary": "one-line gist",            # optional
      "findings": [ {"severity","where","what","impact","value","fix"} ]
    }

Usage:
    review_capture.py --in verdict.json
    cat verdict.json | review_capture.py
    review_capture.py --task T1 --verdict pass --reviewer reviewer-agent   # minimal, no findings

Exits 0 when verdict=pass, 1 when verdict=block (so a blocking review reads as a
failure and cannot be mistaken for a green result).
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from lib import evidence  # noqa: E402


def _now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat()


def _load_verdict(args: argparse.Namespace) -> dict:
    if args.in_path:
        return json.loads(Path(args.in_path).read_text())
    # CLI-flag form wins only when no file/stdin payload is supplied.
    if args.task and args.verdict:
        return {
            "task": args.task,
            "verdict": args.verdict,
            "reviewer": args.reviewer or "",
            "summary": args.summary or "",
            "findings": [],
        }
    raw = sys.stdin.read()
    if not raw.strip():
        raise SystemExit("review_capture: no verdict given (use --in, stdin, or --task/--verdict)")
    return json.loads(raw)


def main() -> int:
    ap = argparse.ArgumentParser(description="Record a signed code-review verdict receipt.")
    ap.add_argument("--in", dest="in_path", default="", help="path to a verdict JSON file")
    ap.add_argument("--task", default="", help="task id (when not using a JSON payload)")
    ap.add_argument("--verdict", choices=["pass", "block"], help="verdict (with --task)")
    ap.add_argument("--reviewer", default="", help="reviewing agent/context id (independence)")
    ap.add_argument("--summary", default="", help="one-line summary (with --task)")
    ap.add_argument("--project", default="", help="project root (default: nearest .temper ancestor)")
    args = ap.parse_args()

    payload = _load_verdict(args)
    task_id = payload.get("task") or payload.get("task_id")
    verdict = payload.get("verdict")
    if not task_id:
        raise SystemExit("review_capture: verdict is missing a 'task' id")
    if verdict not in ("pass", "block"):
        raise SystemExit(f"review_capture: verdict must be 'pass' or 'block', got {verdict!r}")

    root = Path(args.project).resolve() if args.project else evidence.find_project_root()
    record = evidence.build_review_record(
        task_id=task_id,
        verdict=verdict,
        reviewer=payload.get("reviewer", ""),
        summary=payload.get("summary", ""),
        findings=payload.get("findings", []),
        git_state_=evidence.git_state(root),
        created_at=_now(),
    )
    key = evidence.load_or_create_key(root)
    record["signature"] = evidence.sign(record, key)

    out_dir = evidence.evidence_dir(root, task_id)
    out_dir.mkdir(parents=True, exist_ok=True)
    ts = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out_path = out_dir / f"{ts}-review.json"
    out_path.write_text(json.dumps(record, indent=2))

    # Human-readable mirror, so a person browsing .temper/ sees the latest verdict.
    fb_dir = evidence.harness_dir(root) / "eval_feedback"
    fb_dir.mkdir(parents=True, exist_ok=True)
    (fb_dir / f"{task_id}.json").write_text(json.dumps(record, indent=2))

    n = len(record["findings"])
    tag = "PASS" if verdict == "pass" else "BLOCK"
    print(f"[review_capture] {tag} task={task_id} findings={n} -> "
          f"{out_path.relative_to(root)}", file=sys.stderr)
    if verdict == "block":
        print("[review_capture] This verdict BLOCKS: the task cannot be marked passing until "
              "the findings are resolved and review is re-run on the fixed code.", file=sys.stderr)
    return 0 if verdict == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
