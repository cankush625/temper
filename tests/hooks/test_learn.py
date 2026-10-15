"""Tests for hooks/learn.py."""

import json
import os
import subprocess
import sys
import textwrap
import time
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "hooks"))
import learn  # noqa: E402
from lib import config, learn_state, skill_store  # noqa: E402
from tests.support import SKILL_BODY, LearnProject, append_transcript, transcript_lines  # noqa: E402

FAKE_CLAUDE = textwrap.dedent("""\
    #!{python}
    import json, os, sys
    from pathlib import Path
    out = Path(os.environ["FAKE_CLAUDE_DIR"])
    (out / "argv.json").write_text(json.dumps(sys.argv[1:]))
    (out / "stdin.txt").write_text(sys.stdin.read())
    (out / "env.json").write_text(json.dumps({{"child": os.environ.get("TEMPER_LEARN_CHILD")}}))
    intents = json.loads((out / "intents.json").read_text())
    print(json.dumps({{"type": "result", "is_error": False, "total_cost_usd": 0.01,
                      "result": "", "structured_output": {{"intents": intents}}}}))
    """)


class LearnHookTest(unittest.TestCase):
    def setUp(self):
        self.p = LearnProject()
        self.root = self.p.root
        self.fake_dir = self.root.parent / "fake"
        self.fake_dir.mkdir()
        fake = self.fake_dir / "claude"
        fake.write_text(FAKE_CLAUDE.format(python=sys.executable))
        fake.chmod(0o755)
        self.p.config(f'[learn]\nreflect_every = 5\nconsolidate_every = 8\nclaude_bin = "{fake}"')
        self.transcript = self.root.parent / "session.jsonl"
        self.transcript.touch()
        os.environ["FAKE_CLAUDE_DIR"] = str(self.fake_dir)

    def tearDown(self):
        os.environ.pop("FAKE_CLAUDE_DIR", None)
        self.p.close()

    def event(self):
        return {"cwd": str(self.root), "session_id": "s1", "transcript_path": str(self.transcript)}

    def stop(self, *records_lists):
        for records in records_lists:
            append_transcript(self.transcript, records)
        with mock.patch.object(learn, "_spawn") as spawn:
            started = learn.on_stop(self.event())
        return started, spawn

    def session(self):
        with learn_state.locked("project", self.root) as st:
            return dict(learn_state.session(st, "s1")), st["requests"]

    def test_counts_below_threshold_do_not_reflect(self):
        started, spawn = self.stop(transcript_lines("first", 3))
        self.assertEqual(started, [])
        spawn.assert_not_called()
        sess, requests = self.session()
        self.assertEqual((sess["calls"], requests), (3, 1))

    def test_crossing_threshold_writes_redacted_window_and_spawns(self):
        self.stop(transcript_lines("first", 3))
        started, spawn = self.stop(transcript_lines("my key is AKIAIOSFODNN7EXAMPLE", 3))
        self.assertEqual(started, ["reflect"])
        kind, run_id, root = spawn.call_args.args
        self.assertEqual((kind, root), ("reflect", self.root))
        window = (self.root / ".temper" / "learn" / "runs" / f"{run_id}.window.txt").read_text()
        self.assertIn("USER: first", window)
        self.assertNotIn("AKIAIOSFODNN7EXAMPLE", window)
        sess, _ = self.session()
        self.assertEqual((sess["calls"], sess["window_start"]), (0, sess["offset"]))

    def test_next_window_starts_where_the_last_ended(self):
        self.stop(transcript_lines("first", 6))
        _started, spawn = self.stop(transcript_lines("second", 6))
        run_id = spawn.call_args.args[1]
        window = (self.root / ".temper" / "learn" / "runs" / f"{run_id}.window.txt").read_text()
        self.assertNotIn("USER: first", window)
        self.assertIn("USER: second", window)

    def test_force_flag_reflects_early_and_is_cleared(self):
        learn.force_flag(self.root).parent.mkdir(parents=True, exist_ok=True)
        learn.force_flag(self.root).touch()
        started, _spawn = self.stop(transcript_lines("tiny", 1))
        self.assertEqual(started, ["reflect"])
        self.assertFalse(learn.force_flag(self.root).exists())

    def test_curator_needs_two_skills(self):
        started, _ = self.stop(transcript_lines("a", 9))
        self.assertEqual(started, ["reflect"])
        self.p.add_skill("tl-a")
        self.p.add_skill("tl-b")
        started, _ = self.stop(transcript_lines("b", 9))
        self.assertEqual(started, ["reflect", "curate"])

    def test_skill_loads_and_global_requests_are_counted(self):
        self.p.add_skill("tl-plan")
        self.stop(transcript_lines("x", 1, skill="tl-plan"), transcript_lines("y", 0))
        meta = skill_store.find(self.root, "tl-plan").meta
        self.assertEqual(meta["uses"], 1)
        self.assertEqual(learn_state.requests("global", self.root), 2)

    def test_disabled_child_or_no_temper_does_nothing(self):
        self.p.config("[learn]\nenabled = false")
        self.assertEqual(self.stop(transcript_lines("x", 9))[0], [])
        self.p.config("[learn]\nreflect_every = 1")
        with mock.patch.dict(os.environ, {learn.CHILD_ENV: "1"}):
            self.assertEqual(self.stop(transcript_lines("x", 9))[0], [])
        self.assertEqual(learn.on_stop({"cwd": str(self.fake_dir), "session_id": "s",
                                        "transcript_path": str(self.transcript)}), [])

    def test_worker_runs_child_and_records_outcome(self):
        append_transcript(self.transcript, transcript_lines("always read the plan summary before applying", 1))
        (self.fake_dir / "intents.json").write_text(json.dumps([
            {"action": "create", "name": "plan-review", "level": "project", "body": SKILL_BODY,
             "reason": "user rule", "evidence": "always read the plan summary"},
            {"action": "create", "name": "made-up", "level": "project", "body": SKILL_BODY,
             "reason": "guess", "evidence": "nothing like this was ever said"},
        ]))
        run_id = "20261015T000000Z-reflect-abc123"
        window = learn.transcript.render(self.transcript, 0, self.transcript.stat().st_size, 10_000)
        skill_store.write_text(self.root / ".temper" / "learn" / "runs" / f"{run_id}.window.txt", window)
        record = learn.worker("reflect", run_id, self.root)
        self.assertEqual([x["name"] for x in record["landed"]], ["tl-plan-review"])
        self.assertIn("verbatim", record["rejected"][0]["reason"])
        self.assertEqual(record["cost_usd"], 0.01)
        last = json.loads((self.root / ".temper" / "learn" / "last_run.json").read_text())
        self.assertEqual(last["run"], run_id)
        self.assertFalse((self.root / ".temper" / "learn" / "runs" / f"{run_id}.window.txt").exists())
        argv = json.loads((self.fake_dir / "argv.json").read_text())
        self.assertNotIn("--dangerously-skip-permissions", argv)
        self.assertEqual(argv[argv.index("--tools") + 1], "Read,Grep,Glob")
        self.assertEqual(argv[argv.index("--setting-sources") + 1], "user")
        self.assertIn("## Episode", (self.fake_dir / "stdin.txt").read_text())
        self.assertEqual(json.loads((self.fake_dir / "env.json").read_text())["child"], "1")

    def test_worker_curate_snapshots_first(self):
        self.p.add_skill("tl-a")
        self.p.add_skill("tl-b")
        (self.fake_dir / "intents.json").write_text("[]")
        record = learn.worker("curate", "20261015T000000Z-curate-abc123", self.root)
        self.assertEqual(record["landed"], [])
        self.assertTrue(list((self.root / ".temper" / "learn" / "snapshots").glob("*.tar.gz")))
        self.assertIn("## Learned skill index", (self.fake_dir / "stdin.txt").read_text())

    def test_worker_records_child_failure(self):
        self.p.config('[learn]\nclaude_bin = "/nonexistent/claude"')
        run_id = "20261015T000000Z-reflect-def456"
        skill_store.write_text(self.root / ".temper" / "learn" / "runs" / f"{run_id}.window.txt", "USER: hi there")
        record = learn.worker("reflect", run_id, self.root)
        self.assertIn("child did not run", record["error"])

    def test_child_command_global_dir_only_when_enabled(self):
        (self.p.home / "skills").mkdir()
        on = learn.child_command(config.learn({}), "sys", self.root)
        off = learn.child_command(config.learn({"learn": {"global": False}}), "sys", self.root)
        self.assertIn("--add-dir", on)
        self.assertNotIn("--add-dir", off)

    def test_hook_process_end_to_end_spawns_detached_worker(self):
        append_transcript(self.transcript, transcript_lines("always read the plan summary before applying", 6))
        (self.fake_dir / "intents.json").write_text(json.dumps([
            {"action": "create", "name": "plan-review", "level": "project", "body": SKILL_BODY,
             "reason": "user rule", "evidence": "always read the plan summary"}]))
        proc = subprocess.run([sys.executable, str(ROOT / "hooks" / "learn.py")],
                              input=json.dumps(self.event()), capture_output=True, text=True,
                              env={**os.environ})
        self.assertEqual(proc.returncode, 0, proc.stderr)
        last = self.root / ".temper" / "learn" / "last_run.json"
        for _ in range(100):
            if last.exists():
                break
            time.sleep(0.1)
        self.assertEqual(json.loads(last.read_text())["landed"][0]["name"], "tl-plan-review")


if __name__ == "__main__":
    unittest.main()
