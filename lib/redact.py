"""Redaction: scrub secrets and personal data before Temper writes text to disk.

Command receipts keep a tail of the command's stdout/stderr, and review receipts keep the
reviewer's findings, which quote code. Either can carry a credential the command printed or
the code contains. Everything Temper persists passes through `redact()` first.

The rules live in one file, `redaction_rules.toml`. Every rule is matched against the
*original* text and the matched spans are merged before anything is replaced, so one rule's
placeholder can never hide (or split) a secret another rule would have caught.

This is best-effort pattern matching, not a guarantee: it catches the shapes it knows.
"""

from __future__ import annotations

import re
import tomllib
from functools import lru_cache
from pathlib import Path

RULES_PATH = Path(__file__).resolve().parent / "redaction_rules.toml"


def _luhn(text: str) -> bool:
    """
    Whether the digits in `text` pass the Luhn checksum (real card numbers do).

    Example:
        >>> _luhn("4111 1111 1111 1111")
        True
    """

    digits = [int(c) for c in text if c.isdigit()]
    total = 0
    for i, d in enumerate(reversed(digits)):
        if i % 2 == 1:
            d = d * 2 - 9 if d > 4 else d * 2
        total += d
    return bool(digits) and total % 10 == 0


VALIDATORS = {"luhn": _luhn}


@lru_cache(maxsize=1)
def rules() -> tuple[tuple[str, re.Pattern, object], ...]:
    """
    Load and compile the rule set once: a tuple of (label, compiled pattern, validator).

    Example:
        >>> any(label == "secret:jwt" for label, _p, _v in rules())
        True
    """

    data = tomllib.loads(RULES_PATH.read_text())
    out = []
    for category, entries in data.items():
        for entry in entries:
            validator = VALIDATORS.get(entry.get("validate", ""))
            out.append((f"{category}:{entry['name']}", re.compile(entry["pattern"]), validator))
    return tuple(out)


def redact(text: str) -> str:
    """
    Return `text` with every rule match replaced by `[REDACTED:<category>:<name>]`.

    Overlapping matches from different rules collapse into one placeholder, labelled by the
    rule whose match starts first (the longest one on a tie).

    Example:
        >>> redact("key AKIAABCDEFGHIJKLMNOP in output")
        'key [REDACTED:secret:aws_access_key_id] in output'
    """

    if not text:
        return text
    spans: list[tuple[int, int, str]] = []
    for label, pattern, validator in rules():
        for m in pattern.finditer(text):
            if m.end() > m.start() and (validator is None or validator(m.group(0))):
                spans.append((m.start(), m.end(), label))
    if not spans:
        return text
    spans.sort(key=lambda s: (s[0], -s[1]))
    merged: list[list] = []
    for start, end, label in spans:
        if merged and start < merged[-1][1]:
            merged[-1][1] = max(merged[-1][1], end)
        else:
            merged.append([start, end, label])
    parts, pos = [], 0
    for start, end, label in merged:
        parts.append(text[pos:start])
        parts.append(f"[REDACTED:{label}]")
        pos = end
    parts.append(text[pos:])
    return "".join(parts)


def redact_value(value: object) -> object:
    """
    Redact every string inside a JSON-shaped value (dicts, lists, scalars), keeping its shape.

    Example:
        >>> redact_value({"where": "a.py", "what": ["token = abcdefgh12345"]})
        {'where': 'a.py', 'what': ['[REDACTED:secret:credential_assignment]']}
    """

    if isinstance(value, str):
        return redact(value)
    if isinstance(value, dict):
        return {k: redact_value(v) for k, v in value.items()}
    if isinstance(value, list):
        return [redact_value(v) for v in value]
    return value
