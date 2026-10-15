"""Tests for lib/learn_state.py."""

import unittest

from lib import learn_state
from tests.support import LearnProject


class LearnStateTest(unittest.TestCase):
    def setUp(self):
        self.p = LearnProject()

    def tearDown(self):
        self.p.close()

    def test_state_persists_and_sessions_default(self):
        with learn_state.locked("project", self.p.root) as st:
            learn_state.session(st, "s1")["calls"] = 7
            st["requests"] = 3
        with learn_state.locked("project", self.p.root) as st:
            self.assertEqual(st["sessions"]["s1"], {"offset": 0, "window_start": 0, "calls": 7, "curate_calls": 0})
        self.assertEqual(learn_state.requests("project", self.p.root), 3)
        self.assertEqual(learn_state.requests("global", self.p.root), 0)

    def test_sessions_are_bounded(self):
        with learn_state.locked("project", self.p.root) as st:
            for i in range(learn_state.MAX_SESSIONS + 5):
                learn_state.session(st, f"s{i}")["touched"] = f"{i:04}"
        with learn_state.locked("project", self.p.root) as st:
            self.assertEqual(len(st["sessions"]), learn_state.MAX_SESSIONS)
            self.assertNotIn("s0", st["sessions"])

    def test_corrupt_state_starts_fresh(self):
        path = self.p.root / ".temper" / "learn" / "state.json"
        path.parent.mkdir(parents=True)
        path.write_text("{oops")
        with learn_state.locked("project", self.p.root) as st:
            self.assertEqual(st["requests"], 0)


if __name__ == "__main__":
    unittest.main()
