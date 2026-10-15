#!/usr/bin/env python3
"""learn.py — the learning loop: a Stop hook plus the background worker it starts.

Stop hook (default mode). After every turn of a main session it reads the transcript bytes
appended since its last look and:

  - counts tool calls toward the next reflection and the next curator pass;
  - counts user prompts as requests (the lifecycle clock), per layer;
  - counts loads of learned skills (Skill tool calls) into each skill's marker;
  - once `reflect_every` tool calls have passed — or `temper learn --now` asked for it — writes
    the redacted episode and starts a detached reflector worker;
  - once `consolidate_every` tool calls have passed, starts a curator worker.

It never blocks the session: it does bookkeeping, spawns, and exits 0. Fails open.

Worker (`--worker reflect|curate RUN_ID --project ROOT`). Runs a headless `claude -p` child that
can only propose: Read/Grep/Glob tools, no MCP servers, user settings only (so Temper's project
hooks don't run inside it), no session saved, a hard `--max-budget-usd` cap, and a JSON schema
for its answer. The intents go to lib/promoter.py, the only writer. The run's account — what
landed, what was rejected and why, what it cost — goes to .temper/learn/runs/ and last_run.json,
which the session-start hook reports.
"""

from __future__ import annotations

import datetime as dt
import fcntl
import json
import os
import secrets
import subprocess
import sys
from pathlib import Path

TEMPER_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(TEMPER_ROOT))
from lib import (config, evidence, learn_state, promoter, redact, skill_store,  # noqa: E402
                 transcript)

CHILD_ENV = "TEMPER_LEARN_CHILD"
WINDOW_MAX_CHARS = 120_000
CHILD_TIMEOUT_S = 900
PROMPTS = TEMPER_ROOT / "prompts"

INTENT_SCHEMA = {
    "type": "object",
    "properties": {"intents": {"type": "array", "items": {
        "type": "object",
        "properties": {
            "action": {"type": "string", "enum": list(promoter.ACTIONS)},
            "name": {"type": "string"},
            "level": {"type": "string", "enum": list(skill_store.LAYERS)},
            "body": {"type": "string"},
            "old_string": {"type": "string"},
            "new_string": {"type": "string"},
            "absorbed_into": {"type": "string"},
            "reason": {"type": "string"},
            "evidence": {"type": "string"},
        },
        "required": ["action", "name", "reason", "evidence"],
    }}},
    "required": ["intents"],
}


def _runs_dir(root: Path) -> Path:
    return skill_store.state_dir("project", root) / "runs"


def force_flag(root: Path) -> Path:
    """
    The file `temper learn --now` creates to force a reflection at the end of the turn.

    Example:
        >>> force_flag(Path("/repo")).as_posix()
        '/repo/.temper/learn/force'
    """

    return skill_store.state_dir("project", root) / "force"


def _new_run_id(kind: str) -> str:
    stamp = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return f"{stamp}-{kind}-{secrets.token_hex(3)}"


def _spawn(kind: str, run_id: str, root: Path) -> None:
    runs = _runs_dir(root)
    runs.mkdir(parents=True, exist_ok=True)
    with open(runs / f"{run_id}.log", "w") as log:
        subprocess.Popen(
            [sys.executable, str(Path(__file__).resolve()), "--worker", kind, run_id,
             "--project", str(root)],
            stdin=subprocess.DEVNULL, stdout=log, stderr=subprocess.STDOUT,
            start_new_session=True, close_fds=True, env={**os.environ, CHILD_ENV: "1"},
        )


def _count_uses(root: Path, names: list[str], layers: tuple[str, ...]) -> None:
    for name in names:
        skill = skill_store.find(root, name, layers)
        if skill is None:
            continue
        meta = {**skill.meta, "uses": int(skill.meta.get("uses", 0) or 0) + 1,
                "last_used_at": skill_store.now()}
        skill_store.write_json(skill.path / skill_store.MARKER, meta)


def on_stop(event: dict) -> list[str]:
    """
    Do the Stop-hook bookkeeping for one turn; return the worker kinds started.

    Example:
        >>> on_stop({"cwd": "/repo", "session_id": "s1", "transcript_path": "/t.jsonl"})  # doctest: +SKIP
        ['reflect']
    """

    if os.environ.get(CHILD_ENV):
        return []
    root = evidence.find_project_root(event.get("cwd"))
    if not evidence.harness_dir(root).is_dir():
        return []
    settings = config.learn(config.load(root))
    sid, tpath = event.get("session_id"), event.get("transcript_path")
    if not settings["enabled"] or not isinstance(sid, str) or not sid or not tpath \
            or not Path(tpath).is_file():
        return []
    layers = skill_store.LAYERS if settings["global"] else ("project",)
    flag = force_flag(root)

    with learn_state.locked("project", root) as st:
        sess = learn_state.session(st, sid)
        found = transcript.scan(tpath, sess["offset"])
        if found.end < sess["offset"]:  # transcript was rewritten: start the window over
            sess["window_start"] = 0
        sess["offset"] = found.end
        sess["calls"] += found.tool_calls
        sess["curate_calls"] += found.tool_calls
        sess["touched"] = skill_store.now()
        st["requests"] += found.prompts
        window = None
        if sess["calls"] >= settings["reflect_every"] or flag.exists():
            window = (sess["window_start"], sess["offset"])
            sess["window_start"], sess["calls"] = sess["offset"], 0
        curate = sess["curate_calls"] >= settings["consolidate_every"]
        if curate:
            sess["curate_calls"] = 0
    if settings["global"] and found.prompts:
        with learn_state.locked("global", root) as gst:
            gst["requests"] += found.prompts
    _count_uses(root, found.skills, layers)

    started = []
    if window is not None:
        flag.unlink(missing_ok=True)
        text = redact.redact(transcript.render(tpath, window[0], window[1], WINDOW_MAX_CHARS))
        if text.strip():
            run_id = _new_run_id("reflect")
            skill_store.write_text(_runs_dir(root) / f"{run_id}.window.txt", text)
            _spawn("reflect", run_id, root)
            started.append("reflect")
    if curate and len(skill_store.managed(root, layers)) >= 2:
        _spawn("curate", _new_run_id("curate"), root)
        started.append("curate")
    return started


def child_command(settings: dict, system_prompt: str, root: Path) -> list[str]:
    """
    The headless, propose-only `claude` invocation for a worker run.

    Example:
        >>> cmd = child_command(config.learn({}), "sys", Path("/repo"))
        >>> cmd[:4], "--dangerously-skip-permissions" in cmd
        (['claude', '-p', '--model', 'haiku'], False)
    """

    cmd = [settings["claude_bin"], "-p", "--model", settings["model"],
           "--tools", "Read,Grep,Glob",
           "--setting-sources", "user", "--strict-mcp-config", "--no-session-persistence",
           "--max-budget-usd", str(settings["max_budget_usd"]),
           "--output-format", "json", "--json-schema", json.dumps(INTENT_SCHEMA),
           "--append-system-prompt", system_prompt]
    global_skills = skill_store.skills_dir("global", root)
    if settings["global"] and global_skills.is_dir():
        cmd += ["--add-dir", str(global_skills)]
    return cmd


def run_child(settings: dict, system_prompt: str, user_message: str, root: Path) -> tuple[list, dict]:
    """
    Run the child; return (intents, info) where info carries cost and any error.

    Example:
        >>> run_child(settings, "sys", "## Episode ...", root)  # doctest: +SKIP
        ([{'action': 'create', ...}], {'cost_usd': 0.01})
    """

    try:
        proc = subprocess.run(child_command(settings, system_prompt, root), input=user_message,
                              cwd=root, capture_output=True, text=True, timeout=CHILD_TIMEOUT_S,
                              env={**os.environ, CHILD_ENV: "1"})
    except (OSError, subprocess.TimeoutExpired) as exc:
        return [], {"error": f"child did not run: {exc}"}
    try:
        out = json.loads(proc.stdout)
    except json.JSONDecodeError:
        return [], {"error": f"child exit {proc.returncode}, no JSON result: {proc.stderr.strip()[:300]}"}
    info = {"cost_usd": out.get("total_cost_usd")}
    if out.get("is_error"):
        info["error"] = f"child error: {out.get('subtype') or out.get('result')}"
        return [], info
    structured = out.get("structured_output")
    if not isinstance(structured, dict):
        try:
            structured = json.loads(out.get("result") or "")
        except (json.JSONDecodeError, TypeError):
            structured = {}
    intents = structured.get("intents") if isinstance(structured, dict) else None
    return intents if isinstance(intents, list) else [], info


def worker(kind: str, run_id: str, root: Path) -> dict:
    """
    Run one reflect or curate pass end to end and record its account. Returns the record.

    Example:
        >>> worker("reflect", "20261015T101500Z-reflect-a1b2c3", Path("/repo"))  # doctest: +SKIP
        {'run': '...', 'kind': 'reflect', 'landed': [...], 'rejected': [...], 'cost_usd': 0.01}
    """

    settings = config.learn(config.load(root))
    layers = skill_store.LAYERS if settings["global"] else ("project",)
    state = skill_store.state_dir("project", root)
    state.mkdir(parents=True, exist_ok=True)
    window_file = _runs_dir(root) / f"{run_id}.window.txt"
    record = {"run": run_id, "kind": kind, "landed": [], "rejected": []}
    with open(state / ".worker.lock", "w") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)  # one worker at a time per project
        record["at"] = skill_store.now()
        index = "\n".join(skill_store.index_lines(skill_store.managed(root, layers))) or "(none yet)"
        spec = (PROMPTS / "skill-format.md").read_text()
        if kind == "reflect":
            source = window_file.read_text() if window_file.exists() else ""
            system = (PROMPTS / "learn-reflector.md").read_text() + "\n\n" + spec
            message = f"## Existing learned skills\n\n{index}\n\n## Episode\n\n{source}\n"
        else:
            for layer in layers:
                skill_store.snapshot(layer, root)
            source = index
            system = (PROMPTS / "learn-curator.md").read_text() + "\n\n" + spec
            message = f"## Learned skill index\n\n{index}\n"
        if source.strip() and source != "(none yet)":
            intents, info = run_child(settings, system, message, root)
            record.update(info)
            record.update(promoter.apply(intents, root, source, run_id, allow_global=settings["global"]))
        else:
            record["error"] = "nothing to read"
        window_file.unlink(missing_ok=True)
        skill_store.write_json(_runs_dir(root) / f"{run_id}.json", record)
        skill_store.write_json(state / "last_run.json", record)
    return record


def main(argv: list[str]) -> int:
    if len(argv) >= 6 and argv[1] == "--worker" and argv[4] == "--project":
        worker(argv[2], argv[3], Path(argv[5]))
        return 0
    raw = sys.stdin.read()
    on_stop(json.loads(raw) if raw.strip() else {})
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main(sys.argv))
    except SystemExit:
        raise
    except Exception as exc:  # fail OPEN: learning must never trap or break a session
        print(f"[learn] internal error, skipping: {exc}", file=sys.stderr)
        raise SystemExit(0)
