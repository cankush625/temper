"""Tests for bin/temper."""

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
TEMPER = ROOT / "bin" / "temper"


class InitWiresHooksTest(unittest.TestCase):
    def test_init_wires_session_start_once(self):
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp)
            for _ in range(2):  # idempotent
                proc = subprocess.run([sys.executable, str(TEMPER), "init", str(project)],
                                      capture_output=True, text=True)
                self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
            settings = json.loads((project / ".claude" / "settings.local.json").read_text())
            commands = [h["command"] for g in settings["hooks"]["SessionStart"] for h in g["hooks"]]
            self.assertEqual(commands, [f"python3 {ROOT}/hooks/session_start.py"])

    def test_init_wires_learn_hook_and_excludes_learned_skills(self):
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp)
            subprocess.run(["git", "init", "-q", str(project)], check=True)
            subprocess.run([sys.executable, str(TEMPER), "init", str(project)], capture_output=True, check=True)
            settings = json.loads((project / ".claude" / "settings.local.json").read_text())
            stop = [h["command"] for g in settings["hooks"]["Stop"] for h in g["hooks"]]
            self.assertIn(f"python3 {ROOT}/hooks/learn.py", stop)
            self.assertIn(".claude/skills/tl-*", (project / ".git" / "info" / "exclude").read_text())


class LearnCommandTest(unittest.TestCase):
    def run_temper(self, cwd, *args):
        return subprocess.run([sys.executable, str(TEMPER), "learn", *args], cwd=cwd,
                              capture_output=True, text=True)

    def test_now_sets_the_force_flag_and_status_prints(self):
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / ".temper").mkdir()
            self.assertEqual(self.run_temper(tmp, "--now").returncode, 0)
            self.assertTrue((Path(tmp) / ".temper" / "learn" / "force").exists())
            status = self.run_temper(tmp, "status")
            self.assertEqual(status.returncode, 0)
            self.assertIn("(no learned skills yet)", status.stdout)

    def test_requires_temper_dir_and_valid_args(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(self.run_temper(tmp, "--now").returncode, 1)
            (Path(tmp) / ".temper").mkdir()
            self.assertEqual(self.run_temper(tmp, "bogus").returncode, 2)


if __name__ == "__main__":
    unittest.main()
