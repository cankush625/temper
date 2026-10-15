"""Shared helpers for the learning-loop tests: a temp project, a fake transcript, a fake skill."""

import json
import os
import tempfile
from pathlib import Path

SKILL_BODY = "---\ndescription: Use when running terraform plan reviews.\ncategory: infra\n---\nAlways read the plan summary first.\n"


class LearnProject:
    """A temp project with .temper/ and an isolated global home (TEMPER_LEARN_HOME)."""

    def __init__(self):
        self._tmp = tempfile.TemporaryDirectory()
        base = Path(self._tmp.name).resolve()
        self.root = base / "proj"
        (self.root / ".temper").mkdir(parents=True)
        self.home = base / "home"
        self.home.mkdir()
        self._old_home = os.environ.get("TEMPER_LEARN_HOME")
        os.environ["TEMPER_LEARN_HOME"] = str(self.home)

    def close(self):
        if self._old_home is None:
            os.environ.pop("TEMPER_LEARN_HOME", None)
        else:
            os.environ["TEMPER_LEARN_HOME"] = self._old_home
        self._tmp.cleanup()

    def config(self, toml: str) -> None:
        (self.root / "CLAUDE.local.md").write_text(f"## Temper\n\n```toml\n{toml}\n```\n")

    def add_skill(self, name: str, layer: str = "project", body: str = SKILL_BODY, **meta) -> Path:
        base = (self.root / ".claude" if layer == "project" else self.home) / "skills" / name
        base.mkdir(parents=True)
        (base / "SKILL.md").write_text(body.replace("---\n", f"---\nname: {name}\n", 1))
        (base / ".temper-learned.json").write_text(json.dumps(
            {"created_requests": 0, "layer": layer, "uses": 0, "patches": 0, **meta}))
        return base


def transcript_lines(prompt: str, tools: int, reply: str = "done", skill: str = "") -> list[dict]:
    """One user prompt, `tools` tool calls each with a result, an optional Skill load, a reply."""
    out = [{"type": "user", "message": {"role": "user", "content": prompt}}]
    for i in range(tools):
        out.append({"type": "assistant", "message": {"role": "assistant", "content": [
            {"type": "tool_use", "id": f"t{i}", "name": "Bash", "input": {"command": f"echo {i}"}}]}})
        out.append({"type": "user", "message": {"role": "user", "content": [
            {"type": "tool_result", "tool_use_id": f"t{i}", "content": f"out {i}"}]}})
    if skill:
        out.append({"type": "assistant", "message": {"role": "assistant", "content": [
            {"type": "tool_use", "id": "s", "name": "Skill", "input": {"skill": skill}}]}})
    out.append({"type": "assistant", "message": {"role": "assistant", "content": [
        {"type": "text", "text": reply}]}})
    return out


def append_transcript(path: Path, records: list[dict]) -> None:
    with open(path, "a") as f:
        for r in records:
            f.write(json.dumps(r) + "\n")
