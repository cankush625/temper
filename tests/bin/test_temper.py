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


if __name__ == "__main__":
    unittest.main()
