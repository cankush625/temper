"""Tests for lib/skill_store.py."""

import tarfile
import unittest

from lib import skill_store
from tests.support import LearnProject


class SkillStoreTest(unittest.TestCase):
    def setUp(self):
        self.p = LearnProject()

    def tearDown(self):
        self.p.close()

    def test_managed_lists_only_marked_tl_skills(self):
        self.p.add_skill("tl-a")
        self.p.add_skill("tl-b", layer="global")
        mine = self.p.root / ".claude" / "skills" / "tl-hand-written"
        mine.mkdir(parents=True)
        (mine / "SKILL.md").write_text("---\ndescription: mine\n---\nx\n")
        self.assertEqual([(s.name, s.layer) for s in skill_store.managed(self.p.root)],
                         [("tl-a", "project"), ("tl-b", "global")])
        self.assertEqual([s.name for s in skill_store.managed(self.p.root, ("project",))], ["tl-a"])

    def test_frontmatter_and_set_name(self):
        fields, rest = skill_store.frontmatter("---\r\ndescription: d\r\ncategory: c\r\n---\r\nbody\r\n")
        self.assertEqual((fields, rest), ({"description": "d", "category": "c"}, "body\n"))
        self.assertIsNone(skill_store.frontmatter("no frontmatter"))
        self.assertEqual(skill_store.set_name("---\nname: old\ndescription: d\n---\nb", "tl-new"),
                         "---\nname: tl-new\ndescription: d\n---\nb")

    def test_index_groups_by_category_and_cuts_descriptions(self):
        self.p.add_skill("tl-a", body="---\ndescription: " + "x" * 200 + "\ncategory: ops\n---\nb\n")
        self.p.add_skill("tl-b")
        lines = skill_store.index_lines(skill_store.managed(self.p.root), desc_chars=20)
        self.assertEqual(lines[0], "infra:")
        self.assertEqual(lines[2], "ops:")
        self.assertTrue(lines[3].endswith("…"))

    def test_archive_and_snapshot(self):
        self.p.add_skill("tl-a")
        self.p.add_skill("tl-b")
        snap = skill_store.snapshot("project", self.p.root)
        with tarfile.open(snap) as tar:
            self.assertIn("tl-a/SKILL.md", tar.getnames())
        dest = skill_store.archive(skill_store.find(self.p.root, "tl-a"), self.p.root, {"action": "archive"})
        self.assertTrue((dest / "SKILL.md").exists())
        self.assertIsNone(skill_store.find(self.p.root, "tl-a"))

    def test_snapshots_are_bounded(self):
        self.p.add_skill("tl-a")
        for _ in range(skill_store.SNAPSHOTS_KEPT + 3):
            skill_store.snapshot("project", self.p.root)
        snaps = list((self.p.root / ".temper" / "learn" / "snapshots").glob("*.tar.gz"))
        self.assertEqual(len(snaps), skill_store.SNAPSHOTS_KEPT)


if __name__ == "__main__":
    unittest.main()
