"""Tests for lib/lifecycle.py."""

import unittest

from lib import config, learn_state, lifecycle, skill_store
from tests.support import LearnProject


class LifecycleTest(unittest.TestCase):
    def setUp(self):
        self.p = LearnProject()

    def tearDown(self):
        self.p.close()

    def set_requests(self, layer, n):
        with learn_state.locked(layer, self.p.root) as st:
            st["requests"] = n

    def test_probation_protects_new_skills(self):
        self.p.add_skill("tl-new", created_requests=50)
        self.set_requests("project", 120)
        self.assertEqual(lifecycle.run(self.p.root, config.learn({})), [])

    def test_unused_at_maturity_is_archived(self):
        self.p.add_skill("tl-unused")
        self.p.add_skill("tl-used", uses=3)
        self.set_requests("project", 100)
        archived = lifecycle.run(self.p.root, config.learn({}))
        self.assertEqual([a["name"] for a in archived], ["tl-unused"])
        self.assertIsNotNone(skill_store.find(self.p.root, "tl-used"))

    def test_capacity_archives_lowest_rate(self):
        for name, uses in (("tl-a", 1), ("tl-b", 5), ("tl-c", 9)):
            self.p.add_skill(name, uses=uses)
        self.set_requests("project", 200)
        settings = config.learn({"learn": {"capacity_project": 2}})
        self.assertEqual([a["name"] for a in lifecycle.run(self.p.root, settings)], ["tl-a"])

    def test_global_layer_uses_its_own_clock_and_switch(self):
        self.p.add_skill("tl-g", layer="global")
        self.set_requests("global", 299)
        self.assertEqual(lifecycle.run(self.p.root, config.learn({})), [])
        self.set_requests("global", 300)
        self.assertEqual(lifecycle.run(self.p.root, config.learn({"learn": {"global": False}})), [])
        self.assertEqual(len(lifecycle.run(self.p.root, config.learn({}))), 1)


if __name__ == "__main__":
    unittest.main()
