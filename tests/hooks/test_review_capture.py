"""Tests for hooks/review_capture.py."""

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
REVIEW_CAPTURE = ROOT / "hooks" / "review_capture.py"


class ReviewCaptureRedactionTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.project = Path(self._tmp.name)
        (self.project / ".temper").mkdir()

    def tearDown(self):
        self._tmp.cleanup()

    def test_summary_and_findings_are_redacted_in_both_copies(self):
        verdict = {
            "task": "T1", "verdict": "block", "reviewer": "reviewer-agent",
            "summary": "config embeds AKIAIOSFODNN7EXAMPLE",
            "findings": [{"severity": "Must fix", "where": "app.py:3",
                          "what": "hard-coded password = 'hunter2hunter2'"}],
        }
        proc = subprocess.run(
            [sys.executable, str(REVIEW_CAPTURE), "--project", str(self.project)],
            input=json.dumps(verdict), capture_output=True, text=True,
        )
        self.assertEqual(proc.returncode, 1, proc.stderr)
        receipt = next((self.project / ".temper" / "evidence" / "T1").glob("*-review.json"))
        mirror = self.project / ".temper" / "eval_feedback" / "T1.json"
        for path in (receipt, mirror):
            text = path.read_text()
            self.assertNotIn("AKIAIOSFODNN7EXAMPLE", text)
            self.assertNotIn("hunter2hunter2", text)
        record = json.loads(receipt.read_text())
        self.assertEqual(record["findings"][0]["severity"], "Must fix")
        self.assertEqual(record["findings"][0]["where"], "app.py:3")


if __name__ == "__main__":
    unittest.main()
