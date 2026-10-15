"""Tests for lib/gate_log.py."""

import tempfile
import unittest
from pathlib import Path

from lib import gate_log


class GateLogTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        (self.root / ".temper").mkdir()

    def tearDown(self):
        self._tmp.cleanup()

    def test_append_and_recent_round_trip(self):
        gate_log.append(self.root, "evidence_gate", ["a"])
        gate_log.append(self.root, "session_integrity", ["b", "c"])
        got = gate_log.recent(self.root, 5)
        self.assertEqual([e["gate"] for e in got], ["evidence_gate", "session_integrity"])
        self.assertEqual(got[1]["reasons"], ["b", "c"])

    def test_consecutive_duplicate_is_not_repeated(self):
        gate_log.append(self.root, "session_integrity", ["same"])
        gate_log.append(self.root, "session_integrity", ["same"])
        self.assertEqual(len(gate_log.recent(self.root, 5)), 1)

    def test_log_is_bounded(self):
        for i in range(gate_log.MAX_ENTRIES + 10):
            gate_log.append(self.root, "evidence_gate", [str(i)])
        lines = gate_log.log_path(self.root).read_text().splitlines()
        self.assertEqual(len(lines), gate_log.MAX_ENTRIES)
        self.assertEqual(gate_log.recent(self.root, 1)[0]["reasons"], [str(gate_log.MAX_ENTRIES + 9)])

    def test_no_temper_dir_means_no_log(self):
        with tempfile.TemporaryDirectory() as bare:
            gate_log.append(bare, "evidence_gate", ["x"])
            self.assertFalse(gate_log.log_path(bare).exists())

    def test_unreadable_line_is_skipped(self):
        gate_log.append(self.root, "evidence_gate", ["ok"])
        with open(gate_log.log_path(self.root), "a") as f:
            f.write("not json\n")
        self.assertEqual(len(gate_log.recent(self.root, 5)), 1)


if __name__ == "__main__":
    unittest.main()
