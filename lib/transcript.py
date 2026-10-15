"""Reading a Claude Code session transcript (JSONL) for the learning loop.

The Stop hook calls `scan()` on the bytes appended since its last look: it counts tool calls
(the reflection trigger), user prompts (the lifecycle's request count) and Skill loads (a
learned skill's usage). The reflector later gets `render()` of a byte range — a plain-text
episode with tool output cut short — which the caller redacts before anything sees it.

Sidechain records (subagent turns) are ignored: they are not the user's conversation.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

TOOL_INPUT_CHARS = 300
TOOL_RESULT_CHARS = 600
TEXT_CHARS = 4000


@dataclass
class Scan:
    """
    What a slice of transcript contained, and where the slice ended.

    Example:
        >>> Scan(end=10, tool_calls=2, prompts=1, skills=["tl-x"]).tool_calls
        2
    """

    end: int
    tool_calls: int = 0
    prompts: int = 0
    skills: list[str] = field(default_factory=list)


def _records(path: Path, start: int, end: int | None = None):
    """
    Yield the parsed JSON records between byte offsets `start` and `end` (default: EOF).

    Only whole lines are read; a partial trailing line is left for the next call.

    Example:
        >>> list(_records(Path("t.jsonl"), 0))  # doctest: +SKIP
        [(120, {...}), (310, {...})]
    """

    with open(path, "rb") as f:
        f.seek(start)
        pos = start
        while end is None or pos < end:
            line = f.readline()
            if not line or not line.endswith(b"\n"):
                return
            pos += len(line)
            try:
                record = json.loads(line)
            except (json.JSONDecodeError, UnicodeDecodeError):
                continue
            if isinstance(record, dict) and not record.get("isSidechain"):
                yield pos, record


def _blocks(record: dict) -> list:
    content = (record.get("message") or {}).get("content")
    return content if isinstance(content, list) else []


def _is_prompt(record: dict) -> bool:
    if record.get("type") != "user" or record.get("isMeta"):
        return False
    content = (record.get("message") or {}).get("content")
    if isinstance(content, str):
        return bool(content.strip())
    return any(isinstance(b, dict) and b.get("type") == "text" for b in content or [])


def skill_name(tool_input: dict) -> str:
    """
    The skill a Skill tool call loaded, without a leading slash or plugin prefix.

    Example:
        >>> skill_name({"skill": "plugin:tl-deploy"})
        'tl-deploy'
    """

    raw = str(tool_input.get("skill") or tool_input.get("command") or "").strip().lstrip("/")
    return raw.split(":")[-1].split()[0] if raw else ""


def scan(path: str | Path, start: int) -> Scan:
    """
    Count tool calls, user prompts and Skill loads from byte `start` to the last whole line.

    A transcript shorter than `start` (rotated or rewritten) is scanned from the beginning.

    Example:
        >>> scan("session.jsonl", 0).tool_calls  # doctest: +SKIP
        12
    """

    path = Path(path)
    size = path.stat().st_size
    if start > size:
        start = 0
    out = Scan(end=start)
    for pos, record in _records(path, start):
        out.end = pos
        if _is_prompt(record):
            out.prompts += 1
        if record.get("type") != "assistant":
            continue
        for block in _blocks(record):
            if isinstance(block, dict) and block.get("type") == "tool_use":
                out.tool_calls += 1
                if block.get("name") == "Skill" and isinstance(block.get("input"), dict):
                    name = skill_name(block["input"])
                    if name:
                        out.skills.append(name)
    return out


def _cut(text: str, limit: int) -> str:
    text = text.strip()
    return text if len(text) <= limit else text[:limit] + f" …[{len(text) - limit} chars cut]"


def _result_text(block: dict) -> str:
    content = block.get("content")
    if isinstance(content, list):
        return "\n".join(str(c.get("text", "")) for c in content if isinstance(c, dict))
    return str(content or "")


def render(path: str | Path, start: int, end: int, max_chars: int) -> str:
    """
    The episode between two byte offsets as plain text, newest `max_chars` kept.

    User and assistant text is kept (long messages cut), tool calls show their name and a cut
    input, tool results are cut short, and thinking is dropped.

    Example:
        >>> print(render("session.jsonl", 0, 900, 10_000))  # doctest: +SKIP
        USER: make the deploy script idempotent
        TOOL_CALL Read: {"file_path": "deploy.sh"}
        TOOL_RESULT: #!/bin/sh ...
    """

    lines: list[str] = []
    for _pos, record in _records(Path(path), start, end):
        kind = record.get("type")
        content = (record.get("message") or {}).get("content")
        if kind == "user" and isinstance(content, str) and _is_prompt(record):
            lines.append(f"USER: {_cut(content, TEXT_CHARS)}")
            continue
        for block in _blocks(record):
            if not isinstance(block, dict):
                continue
            btype = block.get("type")
            if btype == "text" and kind == "user" and _is_prompt(record):
                lines.append(f"USER: {_cut(str(block.get('text', '')), TEXT_CHARS)}")
            elif btype == "text" and kind == "assistant":
                lines.append(f"ASSISTANT: {_cut(str(block.get('text', '')), TEXT_CHARS)}")
            elif btype == "tool_use":
                args = json.dumps(block.get("input", {}), ensure_ascii=False)
                lines.append(f"TOOL_CALL {block.get('name', '?')}: {_cut(args, TOOL_INPUT_CHARS)}")
            elif btype == "tool_result":
                lines.append(f"TOOL_RESULT: {_cut(_result_text(block), TOOL_RESULT_CHARS)}")
    text = "\n".join(lines)
    return text if len(text) <= max_chars else text[-max_chars:]
