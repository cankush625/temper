"""The promoter: the only code that writes learned skills.

The reflector and the curator are models; they *propose* changes as intents and can write
nothing. This module checks each intent deterministically and lands it, or rejects it with a
reason that the next session sees. An intent is

  {"action": "create" | "update" | "patch" | "archive",
   "name": "<kebab-case>", "level": "project" | "global",        (level: create only)
   "body": "<full SKILL.md>",                                     (create / update)
   "old_string": "...", "new_string": "...",                      (patch)
   "absorbed_into": "<name>",                                     (archive, when merged)
   "reason": "<why>", "evidence": "<verbatim slice of the input>"}

Checks, all of which must pass:

  - the name is kebab-case; it lands as `tl-<name>`;
  - update / patch / archive target a live skill that Temper created (holds the marker);
    create never overwrites anything;
  - the body has frontmatter with a one-line `description` and a `category`, stays within the
    size caps, passes the safety scan, contains nothing the redactor would change, and — for
    the global layer — names no path or repo of this project;
  - `evidence` appears word for word in the text the model was given. A lesson must point at
    something that really happened in the session; an invented quote is rejected.
  - archive's `absorbed_into` names another live managed skill.

Writes are atomic (temp + rename); a new skill is assembled in a hidden folder and renamed into
place, so a half-written skill is never visible to Claude Code.
"""

from __future__ import annotations

import hashlib
import os
import re
import shutil
from pathlib import Path

from . import learn_state, redact, skill_guard, skill_store

NAME_RE = re.compile(r"^[a-z0-9][a-z0-9-]{1,46}[a-z0-9]$")
CATEGORY_RE = re.compile(r"^[a-z][a-z0-9-]{0,31}$")
DESCRIPTION_MAX = 250
BODY_MAX_LINES = 40
BODY_MAX_BYTES = 8000
REASON_MAX = 500
EVIDENCE_MIN, EVIDENCE_MAX = 20, 4000
ACTIONS = ("create", "update", "patch", "archive")


class Rejected(Exception):
    """
    An intent failed a check; the message is the reason recorded for it.

    Example:
        >>> str(Rejected("unknown action"))
        'unknown action'
    """


def _squash(text: str) -> str:
    return " ".join(text.split())


def _full_name(raw: object) -> str:
    name = str(raw or "").strip().lower()
    name = name[len(skill_store.PREFIX):] if name.startswith(skill_store.PREFIX) else name
    if not NAME_RE.match(name):
        raise Rejected(f"name {raw!r} must be kebab-case, 3-48 chars")
    return skill_store.PREFIX + name


def check_body(body: object, layer: str, project_root: Path, repo_name: str) -> str:
    """
    Validate a SKILL.md body for `layer`; return it with `name:` left for the caller to set.

    Example:
        >>> check_body("---\\ndescription: Use when X.\\ncategory: ops\\n---\\nDo Y.\\n",
        ...            "project", Path("/r"), "r")
        '---\\ndescription: Use when X.\\ncategory: ops\\n---\\nDo Y.\\n'
    """

    if not isinstance(body, str) or not body.strip():
        raise Rejected("body is empty")
    body = body.replace("\r\n", "\n")
    parsed = skill_store.frontmatter(body)
    if parsed is None:
        raise Rejected("body has no --- frontmatter --- block")
    fields, rest = parsed
    desc = fields.get("description", "")
    if not desc:
        raise Rejected("frontmatter has no description")
    if len(desc) > DESCRIPTION_MAX:
        raise Rejected(f"description is {len(desc)} chars (max {DESCRIPTION_MAX}); lead with the trigger")
    if not CATEGORY_RE.match(fields.get("category", "")):
        raise Rejected("frontmatter category must be one lowercase word or hyphenated phrase")
    lines = [ln for ln in rest.splitlines() if ln.strip()]
    if not lines:
        raise Rejected("body has no instructions after the frontmatter")
    if len(lines) > BODY_MAX_LINES:
        raise Rejected(f"body is {len(lines)} non-blank lines (max {BODY_MAX_LINES}); state the rule, not the story")
    if len(body.encode()) > BODY_MAX_BYTES:
        raise Rejected(f"body exceeds {BODY_MAX_BYTES} bytes")
    hits = skill_guard.scan(body)
    if hits:
        fam, snippets = next(iter(hits.items()))
        raise Rejected(f"safety scan: {fam} ({snippets[0][:60]!r})")
    if redact.redact(body) != body:
        raise Rejected("body contains a secret or personal data")
    if layer == "global":
        lowered = body.lower()
        if str(project_root).lower() in lowered or (
                len(repo_name) >= 4 and re.search(rf"\b{re.escape(repo_name.lower())}\b", lowered)):
            raise Rejected("a global skill must not name this project's path or repo")
    return body


def _check_evidence(evidence: object, source_text: str) -> str:
    if not isinstance(evidence, str) or len(evidence.strip()) < EVIDENCE_MIN:
        raise Rejected(f"evidence must quote at least {EVIDENCE_MIN} chars of the input")
    if len(evidence) > EVIDENCE_MAX:
        raise Rejected(f"evidence exceeds {EVIDENCE_MAX} chars; quote the decisive slice")
    if _squash(evidence) not in _squash(source_text):
        raise Rejected("evidence is not a verbatim quote of the input")
    return evidence.strip()


def _check_reason(reason: object) -> str:
    if not isinstance(reason, str) or not reason.strip():
        raise Rejected("reason is required")
    if len(reason) > REASON_MAX:
        raise Rejected(f"reason exceeds {REASON_MAX} chars")
    return reason.strip()


def _evidence_file(path: Path, action: str, evidence: str, run_id: str) -> str:
    ref = f"references/evidence-{hashlib.sha256(evidence.encode()).hexdigest()[:12]}.md"
    skill_store.write_text(path / ref, f"# Evidence ({action}, run {run_id})\n\n```\n{evidence}\n```\n")
    return ref


def _record(path: Path, action: str, reason: str, evidence: str, run_id: str) -> None:
    ref = _evidence_file(path, action, evidence, run_id)
    skill_store.append_ledger(path, {"action": action, "reason": reason, "evidence": ref, "run": run_id})


def _create(intent: dict, name: str, project_root: Path, ctx: dict) -> str:
    layer = intent.get("level") or "project"
    if layer not in skill_store.LAYERS:
        raise Rejected("level must be 'project' or 'global'")
    if layer == "global" and not ctx["allow_global"]:
        raise Rejected("the global layer is disabled ([learn] global = false)")
    base = skill_store.skills_dir(layer, project_root)
    if (base / name).exists():
        raise Rejected(f"{name} already exists in the {layer} layer; patch or update it instead")
    body = skill_store.set_name(check_body(intent.get("body"), layer, project_root, ctx["repo_name"]), name)
    tmp = base / f".{name}.tmp-{os.getpid()}"
    shutil.rmtree(tmp, ignore_errors=True)
    tmp.mkdir(parents=True)
    try:
        skill_store.write_text(tmp / "SKILL.md", body)
        skill_store.write_json(tmp / skill_store.MARKER, {
            "created_at": skill_store.now(), "created_requests": learn_state.requests(layer, project_root),
            "layer": layer, "uses": 0, "patches": 0, "run": ctx["run_id"]})
        _record(tmp, "create", ctx["reason"], ctx["evidence"], ctx["run_id"])
        os.rename(tmp, base / name)
    except BaseException:
        shutil.rmtree(tmp, ignore_errors=True)
        raise
    return layer


def _change(intent: dict, action: str, skill: skill_store.Skill, project_root: Path, ctx: dict) -> str:
    if action == "update":
        new = intent.get("body")
    else:
        old, replacement = intent.get("old_string"), intent.get("new_string")
        if not isinstance(old, str) or not old or not isinstance(replacement, str):
            raise Rejected("patch needs a non-empty old_string and a new_string")
        current = skill.body
        if current.count(old) != 1:
            raise Rejected(f"old_string matches {current.count(old)} times in {skill.name}; it must match once")
        new = current.replace(old, replacement, 1)
    body = skill_store.set_name(check_body(new, skill.layer, project_root, ctx["repo_name"]), skill.name)
    skill_store.write_text(skill.path / "SKILL.md", body)
    meta = {**skill.meta, "patches": int(skill.meta.get("patches", 0)) + 1, "patched_at": skill_store.now()}
    skill_store.write_json(skill.path / skill_store.MARKER, meta)
    _record(skill.path, action, ctx["reason"], ctx["evidence"], ctx["run_id"])
    return skill.layer


def _archive(intent: dict, skill: skill_store.Skill, project_root: Path, ctx: dict) -> str:
    umbrella = intent.get("absorbed_into") or ""
    if umbrella:
        umbrella = _full_name(umbrella)
        if umbrella == skill.name or skill_store.find(project_root, umbrella) is None:
            raise Rejected(f"absorbed_into {umbrella!r} is not another live Temper-learned skill")
    ref = _evidence_file(skill.path, "archive", ctx["evidence"], ctx["run_id"])
    skill_store.archive(skill, project_root, {"action": "archive", "absorbed_into": umbrella,
                                               "reason": ctx["reason"], "evidence": ref,
                                               "run": ctx["run_id"]})
    return skill.layer


def apply_one(intent: object, project_root: Path, source_text: str, run_id: str,
              allow_global: bool, repo_name: str) -> dict:
    """
    Check and land one intent. Returns {action, name, layer} or raises Rejected.

    Example:
        >>> apply_one({"action": "drop"}, Path("/r"), "", "run1", True, "r")
        Traceback (most recent call last):
        ...
        lib.promoter.Rejected: unknown action 'drop'
    """

    if not isinstance(intent, dict):
        raise Rejected("intent is not an object")
    action = intent.get("action")
    if action not in ACTIONS:
        raise Rejected(f"unknown action {action!r}")
    name = _full_name(intent.get("name"))
    ctx = {"reason": _check_reason(intent.get("reason")),
           "evidence": _check_evidence(intent.get("evidence"), source_text),
           "run_id": run_id, "allow_global": allow_global, "repo_name": repo_name}
    if action == "create":
        layer = _create(intent, name, project_root, ctx)
    else:
        layers = skill_store.LAYERS if allow_global else ("project",)
        skill = skill_store.find(project_root, name, layers)
        if skill is None:
            raise Rejected(f"{name} is not a live skill Temper created")
        layer = (_archive(intent, skill, project_root, ctx) if action == "archive"
                 else _change(intent, action, skill, project_root, ctx))
    return {"action": action, "name": name, "layer": layer}


def apply(intents: list, project_root: str | Path, source_text: str, run_id: str,
          allow_global: bool = True, repo_name: str = "") -> dict:
    """
    Land each intent in order; return {"landed": [...], "rejected": [...]} for the run record.

    Example:
        >>> apply([{"action": "nope", "name": "x"}], Path("/r"), "", "run1")["rejected"][0]["reason"]
        "unknown action 'nope'"
    """

    root = Path(project_root)
    repo = repo_name or root.name
    result: dict[str, list] = {"landed": [], "rejected": []}
    for intent in intents if isinstance(intents, list) else []:
        try:
            result["landed"].append(apply_one(intent, root, source_text, run_id, allow_global, repo))
        except Rejected as exc:
            name = intent.get("name") if isinstance(intent, dict) else None
            action = intent.get("action") if isinstance(intent, dict) else None
            result["rejected"].append({"action": action, "name": name, "reason": str(exc)})
        except OSError as exc:
            result["rejected"].append({"action": intent.get("action"), "name": intent.get("name"),
                                       "reason": f"write failed: {exc}"})
    return result
