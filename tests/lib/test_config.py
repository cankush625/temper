"""Tests for lib/config.py."""

import unittest

from lib import config


class LearnConfigTest(unittest.TestCase):
    def test_defaults(self):
        self.assertEqual(config.learn({}), config.LEARN_DEFAULTS)

    def test_overrides_and_bad_types_fall_back(self):
        got = config.learn({"learn": {"reflect_every": 10, "enabled": "yes", "model": "",
                                      "max_budget_usd": -1, "capacity_global": True, "global": False}})
        self.assertEqual(got["reflect_every"], 10)
        self.assertTrue(got["enabled"])
        self.assertEqual(got["model"], "haiku")
        self.assertEqual(got["max_budget_usd"], 0.5)
        self.assertEqual(got["capacity_global"], 20)
        self.assertFalse(got["global"])

    def test_non_table_learn_is_ignored(self):
        self.assertEqual(config.learn({"learn": "off"}), config.LEARN_DEFAULTS)


if __name__ == "__main__":
    unittest.main()
