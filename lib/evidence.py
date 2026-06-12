"""Evidence records: the receipts that make "done" verifiable.

An evidence record is written *only* by capture.py after it runs a real command.
It is signed with an HMAC over a per-repo key. The signature is tamper-evidence,
not cryptographic security against a motivated agent that reads the key — its job
is to raise "lazily claim done" into "deliberately forge a signed receipt", which
is a different and far rarer failure.

Freshness is the stronger guarantee: every record pins the project's code state
(git sha + a digest of the working-tree diff, excluding the .temper/ bookkeeping
dir). If code changes after capture, the digest no longer matches and the evidence
is rejected as stale. Editing plans/progress/evidence does not invalidate evidence.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import subprocess
from pathlib import Path

HARNESS_DIRNAME = ".temper"
EVIDENCE_DIRNAME = "evidence"
KEY_FILENAME = ".capture_key"
SCHEMA_VERSION = 1


def harness_dir(project_root: str | Path) -> Path:
    return Path(project_root) / HARNESS_DIRNAME


def find_project_root(start: str | Path | None = None) -> Path:
    """Walk upward from `start` (default cwd) to find a dir containing .temper/."""
    cur = Path(start or os.getcwd()).resolve()
    for candidate in [cur, *cur.parents]:
        if (candidate / HARNESS_DIRNAME).is_dir():
            return candidate
    # Fall back to cwd so first-time `capture` in a fresh project still works.
    return cur


# --------------------------------------------------------------------------- #
# Signing
# --------------------------------------------------------------------------- #
def _key_path(project_root: str | Path) -> Path:
    return harness_dir(project_root) / KEY_FILENAME


def load_or_create_key(project_root: str | Path) -> bytes:
    path = _key_path(project_root)
    if path.exists():
        return bytes.fromhex(path.read_text().strip())
    path.parent.mkdir(parents=True, exist_ok=True)
    key = os.urandom(32)
    path.write_text(key.hex())
    os.chmod(path, 0o600)
    return key


def _canonical(record: dict) -> bytes:
    body = {k: v for k, v in record.items() if k != "signature"}
    return json.dumps(body, sort_keys=True, separators=(",", ":")).encode("utf-8")


def sign(record: dict, key: bytes) -> str:
    return hmac.new(key, _canonical(record), hashlib.sha256).hexdigest()


def verify_signature(record: dict, key: bytes) -> bool:
    sig = record.get("signature")
    if not isinstance(sig, str):
        return False
    return hmac.compare_digest(sig, sign(record, key))


# --------------------------------------------------------------------------- #
# Git / working-tree state
# --------------------------------------------------------------------------- #
def _git(root: str | Path, *args: str) -> str:
    try:
        out = subprocess.run(
            ["git", "-C", str(root), *args],
            capture_output=True, text=True, check=False,
        )
        return out.stdout
    except FileNotFoundError:
        return ""


def git_state(project_root: str | Path) -> dict:
    """Code state used to pin evidence to a moment in the source tree.

    Excludes the .temper/ dir so that writing plans/evidence/progress (normal
    Temper bookkeeping) does not invalidate previously captured receipts.
    """
    root = Path(project_root)
    sha = _git(root, "rev-parse", "HEAD").strip() or "NO_HEAD"

    porcelain = _git(root, "status", "--porcelain")
    code_lines = [
        ln for ln in porcelain.splitlines()
        if HARNESS_DIRNAME + "/" not in ln
    ]
    diff = _git(root, "diff", "HEAD", "--", ".", f":(exclude){HARNESS_DIRNAME}")

    digest_input = ("\n".join(sorted(code_lines)) + "\n---DIFF---\n" + diff).encode("utf-8")
    tree_digest = hashlib.sha256(digest_input).hexdigest()
    dirty = bool(code_lines)
    return {"sha": sha, "dirty": dirty, "tree_digest": tree_digest}


# --------------------------------------------------------------------------- #
# Evidence read / lookup
# --------------------------------------------------------------------------- #
def evidence_dir(project_root: str | Path, task_id: str) -> Path:
    return harness_dir(project_root) / EVIDENCE_DIRNAME / task_id


def load_evidence_file(path: str | Path) -> dict | None:
    try:
        return json.loads(Path(path).read_text())
    except (OSError, json.JSONDecodeError):
        return None


def is_valid_for_state(record: dict, key: bytes, current: dict) -> bool:
    """A record proves the current code state iff it is signed, succeeded, and
    pins exactly the current sha + tree digest."""
    if not isinstance(record, dict):
        return False
    if not verify_signature(record, key):
        return False
    if record.get("exit_code") != 0:
        return False
    gs = record.get("git_state") or {}
    return gs.get("sha") == current["sha"] and gs.get("tree_digest") == current["tree_digest"]


def valid_evidence_for_task(project_root: str | Path, task_id: str) -> list[dict]:
    """Return all on-disk evidence records that currently prove task_id passing."""
    root = Path(project_root)
    key = load_or_create_key(root)
    current = git_state(root)
    found = []
    d = evidence_dir(root, task_id)
    if not d.is_dir():
        return found
    for f in sorted(d.glob("*.json")):
        rec = load_evidence_file(f)
        if rec and rec.get("task_id") == task_id and is_valid_for_state(rec, key, current):
            found.append(rec)
    return found
