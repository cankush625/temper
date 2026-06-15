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

# Two kinds of receipt prove two different things, and a task needs BOTH to pass:
#   command receipts  (baseline / verify) — a real command exited 0 on this tree.
#   review receipts   (review)            — a fresh-context review returned verdict=pass.
# Keeping them in separate namespaces stops a green-test receipt from standing in for
# a review (or vice-versa): the gate must see one of each, pinned to the same tree.
COMMAND_KINDS = ("baseline", "verify")
REVIEW_KIND = "review"


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


def working_diff(project_root: str | Path) -> str:
    """The working-tree diff vs HEAD, excluding the .temper/ bookkeeping dir — the same
    view git_state digests. Used by checks that need to inspect *what* changed."""
    root = Path(project_root)
    return _git(root, "diff", "HEAD", "--", ".", f":(exclude){HARNESS_DIRNAME}")


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


def _pins_current(record: dict, current: dict) -> bool:
    gs = record.get("git_state") or {}
    return gs.get("sha") == current["sha"] and gs.get("tree_digest") == current["tree_digest"]


def is_valid_for_state(record: dict, key: bytes, current: dict) -> bool:
    """A command receipt proves the current code state iff it is signed, is a command
    receipt (baseline/verify), succeeded (exit 0), and pins the current sha + tree digest."""
    if not isinstance(record, dict):
        return False
    if not verify_signature(record, key):
        return False
    if record.get("kind", "verify") not in COMMAND_KINDS:
        return False
    if record.get("exit_code") != 0:
        return False
    return _pins_current(record, current)


# Reviewer ids that mean "the author graded their own homework" — rejected when the
# two-key independence rule is on. A real review names a distinct fresh-context reviewer.
AUTHOR_SENTINELS = {"", "author", "self", "implementer", "unspecified", "me", "same", "tp-impl"}


def reviewer_is_independent(record: dict) -> bool:
    return str(record.get("reviewer", "")).strip().lower() not in AUTHOR_SENTINELS


def is_valid_review_for_state(record: dict, key: bytes, current: dict,
                              require_independent: bool = False) -> bool:
    """A review receipt proves the current code state iff it is signed, is a review
    receipt, carries verdict=pass, pins the current sha + tree digest, and (when
    require_independent) names a reviewer distinct from the author."""
    if not isinstance(record, dict):
        return False
    if not verify_signature(record, key):
        return False
    if record.get("kind") != REVIEW_KIND:
        return False
    if record.get("verdict") != "pass":
        return False
    if require_independent and not reviewer_is_independent(record):
        return False
    return _pins_current(record, current)


def _scan(project_root: str | Path, task_id: str, predicate) -> list[dict]:
    root = Path(project_root)
    key = load_or_create_key(root)
    current = git_state(root)
    found = []
    d = evidence_dir(root, task_id)
    if not d.is_dir():
        return found
    for f in sorted(d.glob("*.json")):
        rec = load_evidence_file(f)
        if rec and rec.get("task_id") == task_id and predicate(rec, key, current):
            found.append(rec)
    return found


def valid_evidence_for_task(project_root: str | Path, task_id: str) -> list[dict]:
    """On-disk command receipts that currently prove task_id's checks pass."""
    return _scan(project_root, task_id, is_valid_for_state)


def valid_review_for_task(project_root: str | Path, task_id: str,
                          require_independent: bool = False) -> list[dict]:
    """On-disk review receipts that currently prove task_id passed review."""
    def predicate(rec, key, current):
        return is_valid_review_for_state(rec, key, current, require_independent)
    return _scan(project_root, task_id, predicate)


def build_review_record(
    task_id: str,
    verdict: str,
    reviewer: str,
    summary: str,
    findings: list,
    git_state_: dict,
    created_at: str,
    rubric: str = "thermo-nuclear+superset",
) -> dict:
    """Assemble (unsigned) a review receipt. The caller signs it with the repo key.
    `verdict` is "pass" or "block"; exit_code mirrors it so a block reads as failure."""
    return {
        "schema_version": SCHEMA_VERSION,
        "task_id": task_id,
        "kind": REVIEW_KIND,
        "verdict": verdict,
        "reviewer": reviewer or "unspecified",
        "rubric": rubric,
        "summary": summary,
        "findings": findings,
        "exit_code": 0 if verdict == "pass" else 1,
        "created_at": created_at,
        "git_state": git_state_,
    }
