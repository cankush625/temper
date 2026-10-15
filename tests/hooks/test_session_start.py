"""Tests for hooks/session_start.py."""

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
HOOK = ROOT / "hooks" / "session_start.py"
sys.path.insert(0, str(ROOT / "hooks"))
import session_start  # noqa: E402
from lib import gate_log  # noqa: E402


def _plan(*tasks: tuple[str, str]) -> str:
    return json.dumps({"slug": "demo", "tasks": [
        {"id": tid, "title": f"title {tid}", "status": status, "evidence": []} for tid, status in tasks]})


class SessionStartTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        (self.root / ".temper" / "plans").mkdir(parents=True)

    def tearDown(self):
        self._tmp.cleanup()

    def _run(self) -> subprocess.CompletedProcess:
        return subprocess.run([sys.executable, str(HOOK)], input=json.dumps({"cwd": str(self.root)}),
                              capture_output=True, text=True)

    def test_no_plans_adds_nothing(self):
        proc = self._run()
        self.assertEqual(proc.returncode, 0)
        self.assertEqual(proc.stdout, "")

    def test_no_temper_dir_adds_nothing(self):
        with tempfile.TemporaryDirectory() as bare:
            self.assertEqual(session_start.build_context(Path(bare)), "")

    def test_reports_progress_and_next_open_task(self):
        (self.root / ".temper" / "plans" / "demo.json").write_text(
            _plan(("T1", "failing"), ("T2", "failing")))
        proc = self._run()
        out = json.loads(proc.stdout)["hookSpecificOutput"]
        self.assertEqual(out["hookEventName"], "SessionStart")
        self.assertIn('- demo: 0/2 passing; next: T1 "title T1"', out["additionalContext"])

    def test_reports_passing_claim_without_receipts(self):
        (self.root / ".temper" / "plans" / "demo.json").write_text(_plan(("T1", "passing")))
        ctx = session_start.build_context(self.root)
        self.assertIn("Stop hook would reject now", ctx)
        self.assertIn("'T1'", ctx)

    def test_reports_recent_gate_blocks(self):
        (self.root / ".temper" / "plans" / "demo.json").write_text(_plan(("T1", "failing")))
        gate_log.append(self.root, "evidence_gate", ["first reason", "second reason"])
        ctx = session_start.build_context(self.root)
        self.assertIn("evidence_gate: first reason (+1 more)", ctx)

    def test_invalid_plan_is_reported_not_raised(self):
        (self.root / ".temper" / "plans" / "bad.json").write_text("{nope")
        proc = self._run()
        self.assertEqual(proc.returncode, 0)
        self.assertIn("bad: unreadable", json.loads(proc.stdout)["hookSpecificOutput"]["additionalContext"])

    def test_context_is_capped(self):
        for i in range(session_start.MAX_LINES + 5):
            (self.root / ".temper" / "plans" / f"p{i:02}.json").write_text(_plan(("T1", "failing")))
        lines = session_start.build_context(self.root).splitlines()
        self.assertEqual(len(lines), session_start.MAX_LINES)
        self.assertIn("more lines", lines[-1])


class GatesWriteTheLogTest(unittest.TestCase):
    def test_session_integrity_block_is_logged(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / ".temper" / "plans").mkdir(parents=True)
            (root / ".temper" / "plans" / "demo.json").write_text(_plan(("T1", "passing")))
            proc = subprocess.run([sys.executable, str(ROOT / "hooks" / "session_integrity.py")],
                                  input=json.dumps({"cwd": str(root)}), capture_output=True, text=True)
            self.assertEqual(proc.returncode, 2)
            self.assertEqual(gate_log.recent(root, 1)[0]["gate"], "session_integrity")

    def test_evidence_gate_block_is_logged(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            plan = root / ".temper" / "plans" / "demo.json"
            plan.parent.mkdir(parents=True)
            plan.write_text(_plan(("T1", "failing")))
            event = {"cwd": str(root), "tool_name": "Write",
                     "tool_input": {"file_path": str(plan), "content": _plan(("T1", "passing"))}}
            proc = subprocess.run([sys.executable, str(ROOT / "hooks" / "evidence_gate.py")],
                                  input=json.dumps(event), capture_output=True, text=True)
            self.assertEqual(proc.returncode, 2)
            self.assertEqual(gate_log.recent(root, 1)[0]["gate"], "evidence_gate")


if __name__ == "__main__":
    unittest.main()
