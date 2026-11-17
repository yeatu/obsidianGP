"""Exact UTF-8 content integrity checks."""

from __future__ import annotations

import hashlib


def content_hash(raw_text: str) -> str:
    if not isinstance(raw_text, str):
        raise TypeError("raw_text must be str")
    return "sha256:" + hashlib.sha256(raw_text.encode("utf-8")).hexdigest()


def matches_content_hash(raw_text: str, expected_hash: str) -> bool:
    return content_hash(raw_text) == expected_hash.lower()
