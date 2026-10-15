"""Tests for lib/transcript.py."""

import json
import tempfile
import unittest
from pathlib import Path

from lib import transcript
from tests.support import append_transcript, transcript_lines


class TranscriptTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.path = Path(self._tmp.name) / "t.jsonl"

    def tearDown(self):
        self._tmp.cleanup()

    def test_scan_counts_tools_prompts_and_skills(self):
        append_transcript(self.path, transcript_lines("fix it", 3, skill="tl-infra"))
        found = transcript.scan(self.path, 0)
        self.assertEqual((found.tool_calls, found.prompts, found.skills), (4, 1, ["tl-infra"]))
        self.assertEqual(found.end, self.path.stat().st_size)

    def test_scan_from_offset_sees_only_new_records(self):
        append_transcript(self.path, transcript_lines("one", 2))
        first = transcript.scan(self.path, 0)
        append_transcript(self.path, transcript_lines("two", 1))
        second = transcript.scan(self.path, first.end)
        self.assertEqual((second.tool_calls, second.prompts), (1, 1))

    def test_partial_trailing_line_is_left_for_later(self):
        append_transcript(self.path, transcript_lines("one", 1))
        size = self.path.stat().st_size
        with open(self.path, "a") as f:
            f.write('{"type": "user"')
        self.assertEqual(transcript.scan(self.path, 0).end, size)

    def test_sidechain_and_tool_results_are_not_prompts(self):
        records = transcript_lines("real", 1)
        records.append({"type": "user", "isSidechain": True, "message": {"content": "subagent"}})
        append_transcript(self.path, records)
        self.assertEqual(transcript.scan(self.path, 0).prompts, 1)

    def test_offset_past_end_rescans_from_start(self):
        append_transcript(self.path, transcript_lines("one", 2))
        self.assertEqual(transcript.scan(self.path, 10**9).tool_calls, 2)

    def test_render_shows_conversation_and_cuts_tool_output(self):
        records = transcript_lines("please make deploys idempotent", 1, reply="Use set -e first.")
        records[2]["message"]["content"][0]["content"] = "x" * 5000
        append_transcript(self.path, records)
        text = transcript.render(self.path, 0, self.path.stat().st_size, 100_000)
        self.assertIn("USER: please make deploys idempotent", text)
        self.assertIn('TOOL_CALL Bash: {"command": "echo 0"}', text)
        self.assertIn("chars cut]", text)
        self.assertIn("ASSISTANT: Use set -e first.", text)

    def test_render_keeps_newest_chars(self):
        append_transcript(self.path, transcript_lines("old prompt", 0, reply="newest reply"))
        text = transcript.render(self.path, 0, self.path.stat().st_size, 12)
        self.assertEqual(text, "newest reply")

    def test_skill_name_strips_prefixes(self):
        self.assertEqual(transcript.skill_name({"skill": "/tl-x"}), "tl-x")
        self.assertEqual(transcript.skill_name({"command": "plugin:tl-y args"}), "tl-y")
        self.assertEqual(transcript.skill_name({}), "")

    def test_bad_json_line_is_skipped(self):
        with open(self.path, "w") as f:
            f.write("not json\n" + json.dumps(transcript_lines("p", 1)[1]) + "\n")
        self.assertEqual(transcript.scan(self.path, 0).tool_calls, 1)


if __name__ == "__main__":
    unittest.main()
