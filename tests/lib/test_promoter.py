"""Tests for lib/promoter.py."""

import json
import unittest

from lib import promoter, skill_store
from tests.support import SKILL_BODY, LearnProject

SOURCE = "USER: always read the terraform plan summary before applying, never skim it"
EVIDENCE = "always read the terraform plan summary"


def intent(**kw):
    base = {"action": "create", "name": "plan-review", "level": "project", "body": SKILL_BODY,
            "reason": "user correction", "evidence": EVIDENCE}
    base.update(kw)
    return base


class PromoterTest(unittest.TestCase):
    def setUp(self):
        self.p = LearnProject()
        self.root = self.p.root

    def tearDown(self):
        self.p.close()

    def apply(self, *intents, source=SOURCE, allow_global=True):
        return promoter.apply(list(intents), self.root, source, "run1", allow_global=allow_global)

    def rejected_reason(self, result):
        self.assertEqual(result["landed"], [], result)
        return result["rejected"][0]["reason"]

    def test_create_lands_with_marker_ledger_and_evidence(self):
        result = self.apply(intent())
        self.assertEqual(result["landed"], [{"action": "create", "name": "tl-plan-review", "layer": "project"}])
        path = self.root / ".claude" / "skills" / "tl-plan-review"
        self.assertTrue((path / "SKILL.md").read_text().startswith("---\nname: tl-plan-review\n"))
        self.assertTrue(skill_store.is_managed(path))
        entry = json.loads((path / ".ledger.jsonl").read_text().splitlines()[0])
        self.assertEqual(entry["action"], "create")
        self.assertIn(EVIDENCE, (path / entry["evidence"]).read_text())
        self.assertEqual(list(path.parent.glob(".tl-*")), [])  # no temp folder left behind

    def test_create_global_lands_in_global_home(self):
        self.apply(intent(level="global"))
        self.assertTrue((self.p.home / "skills" / "tl-plan-review" / "SKILL.md").exists())

    def test_global_disabled_rejects(self):
        self.assertIn("global layer is disabled",
                      self.rejected_reason(self.apply(intent(level="global"), allow_global=False)))

    def test_evidence_must_be_verbatim(self):
        reason = self.rejected_reason(self.apply(intent(evidence="the user said to read plans carefully")))
        self.assertIn("not a verbatim quote", reason)

    def test_evidence_matches_across_whitespace(self):
        self.assertEqual(len(self.apply(intent(evidence="always  read the\nterraform plan summary"))["landed"]), 1)

    def test_short_evidence_rejected(self):
        self.assertIn("at least", self.rejected_reason(self.apply(intent(evidence="always"))))

    def test_bad_names_rejected(self):
        for name in ("Plan Review", "x", "../escape", "a" * 60):
            self.assertIn("kebab-case", self.rejected_reason(self.apply(intent(name=name))), name)

    def test_create_never_overwrites(self):
        (self.root / ".claude" / "skills" / "tl-plan-review").mkdir(parents=True)
        self.assertIn("already exists", self.rejected_reason(self.apply(intent())))

    def test_body_checks(self):
        cases = {
            "no --- frontmatter": "just text",
            "no description": "---\ncategory: infra\n---\nDo it.\n",
            "category must be": "---\ndescription: Use when x.\ncategory: Infra Ops\n---\nDo it.\n",
            "description is": "---\ndescription: " + "d" * 300 + "\ncategory: infra\n---\nDo it.\n",
            "non-blank lines": "---\ndescription: Use when x.\ncategory: infra\n---\n" + "line\n" * 41,
            "no instructions": "---\ndescription: Use when x.\ncategory: infra\n---\n\n",
            "safety scan": "---\ndescription: Use when x.\ncategory: infra\n---\nCommit with --no-verify.\n",
            "secret or personal": "---\ndescription: Use when x.\ncategory: infra\n---\nMail dev@example.com.\n",
        }
        for expected, body in cases.items():
            self.assertIn(expected, self.rejected_reason(self.apply(intent(body=body))), expected)

    def test_global_skill_must_not_name_the_project(self):
        body = SKILL_BODY + f"Look in {self.root}/infra.\n"
        self.assertIn("must not name", self.rejected_reason(self.apply(intent(level="global", body=body))))

    def test_patch_updates_marker_and_ledger(self):
        self.p.add_skill("tl-plan-review")
        result = self.apply(intent(action="patch", old_string="Always read", new_string="Always open and read"))
        self.assertEqual(len(result["landed"]), 1, result)
        path = self.root / ".claude" / "skills" / "tl-plan-review"
        self.assertIn("Always open and read", (path / "SKILL.md").read_text())
        self.assertEqual(json.loads((path / ".temper-learned.json").read_text())["patches"], 1)

    def test_patch_old_string_must_match_once(self):
        self.p.add_skill("tl-plan-review")
        self.assertIn("matches 0 times", self.rejected_reason(
            self.apply(intent(action="patch", old_string="missing", new_string="x"))))

    def test_update_replaces_body(self):
        self.p.add_skill("tl-plan-review")
        body = SKILL_BODY.replace("first", "before anything else")
        self.assertEqual(len(self.apply(intent(action="update", body=body))["landed"]), 1)

    def test_unmanaged_skill_is_never_touched(self):
        path = self.root / ".claude" / "skills" / "tl-plan-review"
        path.mkdir(parents=True)
        (path / "SKILL.md").write_text(SKILL_BODY)
        for action in ("patch", "update", "archive"):
            reason = self.rejected_reason(self.apply(intent(action=action, old_string="Always", new_string="A")))
            self.assertIn("not a live skill Temper created", reason)
        self.assertEqual((path / "SKILL.md").read_text(), SKILL_BODY)

    def test_archive_moves_out_of_recall_with_umbrella(self):
        self.p.add_skill("tl-plan-review")
        self.p.add_skill("tl-terraform")
        result = self.apply(intent(action="archive", absorbed_into="terraform"))
        self.assertEqual(len(result["landed"]), 1, result)
        self.assertFalse((self.root / ".claude" / "skills" / "tl-plan-review").exists())
        archived = next((self.root / ".temper" / "learn" / "archive").glob("tl-plan-review-*"))
        entry = json.loads((archived / ".ledger.jsonl").read_text().splitlines()[-1])
        self.assertEqual(entry["absorbed_into"], "tl-terraform")

    def test_archive_into_unknown_umbrella_rejected(self):
        self.p.add_skill("tl-plan-review")
        self.assertIn("absorbed_into", self.rejected_reason(self.apply(intent(action="archive", absorbed_into="nope"))))
        self.assertTrue((self.root / ".claude" / "skills" / "tl-plan-review").exists())

    def test_intents_apply_in_order_and_independently(self):
        result = self.apply(intent(), intent(name="other-skill", evidence="made up evidence text here"),
                            intent(action="patch", old_string="Always read", new_string="Read"))
        self.assertEqual([x["action"] for x in result["landed"]], ["create", "patch"])
        self.assertEqual(len(result["rejected"]), 1)

    def test_garbage_intents_are_rejected_not_raised(self):
        result = promoter.apply(["nope", {"action": "create"}], self.root, SOURCE, "run1")
        self.assertEqual(len(result["rejected"]), 2)
        self.assertEqual(promoter.apply("not a list", self.root, SOURCE, "run1"), {"landed": [], "rejected": []})


if __name__ == "__main__":
    unittest.main()
