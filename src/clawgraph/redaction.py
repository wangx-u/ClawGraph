"""Generic redaction helpers for judge and workflow preparation."""

from __future__ import annotations

import re
from collections import Counter
from typing import Iterable

_SECRET_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("openai_key", re.compile(r"\bsk-[A-Za-z0-9]{16,}\b")),
    ("aws_access_key", re.compile(r"\bAKIA[0-9A-Z]{16}\b")),
    ("github_token", re.compile(r"\bgh[pousr]_[A-Za-z0-9]{20,}\b")),
    ("private_key", re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----")),
    ("bearer_token", re.compile(r"\bBearer\s+[A-Za-z0-9._\-]{24,}\b", re.IGNORECASE)),
)


def find_secret_like_matches(text: str | None) -> dict[str, int]:
    """Return pattern counts for one text blob."""

    if not isinstance(text, str) or not text:
        return {}
    counts: Counter[str] = Counter()
    for label, pattern in _SECRET_PATTERNS:
        match_count = len(pattern.findall(text))
        if match_count:
            counts[label] += match_count
    return dict(counts)


def summarize_secret_like_matches(texts: Iterable[str | None]) -> dict[str, int]:
    """Aggregate secret-like pattern counts across multiple texts."""

    counts: Counter[str] = Counter()
    for text in texts:
        counts.update(find_secret_like_matches(text))
    return dict(counts)


def redact_secret_like_text(text: str | None) -> str | None:
    """Mask secret-like substrings before sending text to external judges."""

    if not isinstance(text, str) or not text:
        return text
    redacted = text
    for label, pattern in _SECRET_PATTERNS:
        redacted = pattern.sub(f"<redacted:{label}>", redacted)
    return redacted
