"""Tests for hooks/capture.py."""

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CAPTURE = ROOT / "hooks" / "capture.py"


def _run_capture(project: Path, *command: str) -> tuple[subprocess.CompletedProcess, dict]:
    proc = subprocess.run(
        [sys.executable, str(CAPTURE), "--task", "T1", "--claim", "password=abcdefgh123",
         "--project", str(project), "--", *command],
        capture_output=True, text=True,
    )
    receipt = next((project / ".temper" / "evidence" / "T1").glob("*.json"))
    return proc, json.loads(receipt.read_text())


class CaptureRedactionTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.project = Path(self._tmp.name)
        (self.project / ".temper").mkdir()

    def tearDown(self):
        self._tmp.cleanup()

    def test_receipt_tails_are_redacted_but_live_output_is_not(self):
        script = "print('key AKIAIOSFODNN7EXAMPLE'); import sys; print('dev@example.com', file=sys.stderr)"
        proc, receipt = _run_capture(self.project, sys.executable, "-c", script)
        self.assertEqual(proc.returncode, 0)
        self.assertIn("AKIAIOSFODNN7EXAMPLE", proc.stdout)
        self.assertNotIn("AKIA", receipt["stdout_tail"])
        self.assertIn("[REDACTED:secret:aws_access_key_id]", receipt["stdout_tail"])
        self.assertNotIn("dev@example.com", receipt["stderr_tail"])

    def test_raw_output_hash_is_kept(self):
        import hashlib
        proc, receipt = _run_capture(self.project, sys.executable, "-c", "print('AKIAIOSFODNN7EXAMPLE')")
        self.assertEqual(receipt["stdout_sha256"], hashlib.sha256(proc.stdout.encode()).hexdigest())

    def test_command_and_claim_are_redacted(self):
        _proc, receipt = _run_capture(self.project, sys.executable, "-c", "pass", "--token=abcdefgh12345")
        self.assertNotIn("abcdefgh12345", json.dumps(receipt["command"]))
        self.assertNotIn("abcdefgh123", receipt["claim"])

    def test_secret_starting_before_the_tail_cut_is_still_redacted(self):
        script = ("print('-----BEGIN RSA PRIVATE KEY-----'); print('A' * 5000); "
                  "print('-----END RSA PRIVATE KEY-----')")
        _proc, receipt = _run_capture(self.project, sys.executable, "-c", script)
        self.assertNotIn("AAAA", receipt["stdout_tail"])

    def test_exit_code_is_the_commands_own(self):
        proc, receipt = _run_capture(self.project, sys.executable, "-c", "raise SystemExit(3)")
        self.assertEqual(proc.returncode, 3)
        self.assertEqual(receipt["exit_code"], 3)


if __name__ == "__main__":
    unittest.main()
