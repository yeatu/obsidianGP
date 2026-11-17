"""Explicit token accounting. No character-count fallback is permitted."""

from __future__ import annotations

from dataclasses import dataclass
from importlib.metadata import PackageNotFoundError, version
from typing import Any


@dataclass(frozen=True)
class TokenCount:
    value: int
    tokenizer_name: str
    tokenizer_version: str
    encoding: str
    exact_for_encoding: bool
    exact_for_client_model: bool


class TokenCounter:
    """tiktoken-backed token counter with an explicit encoding."""

    def __init__(self, encoding: str = "o200k_base") -> None:
        try:
            import tiktoken
        except ImportError as exc:
            raise RuntimeError(
                "tiktoken is required for Context Builder budget accounting"
            ) from exc
        try:
            self._encoding = tiktoken.get_encoding(encoding)
        except Exception as exc:
            raise RuntimeError(f"Unsupported tiktoken encoding: {encoding}") from exc
        self._encoding_name = encoding
        try:
            self._version = version("tiktoken")
        except PackageNotFoundError:
            self._version = "unknown"

    def count(self, text: str) -> int:
        if not isinstance(text, str):
            raise TypeError("TokenCounter.count expects str")
        return len(self._encoding.encode(text, disallowed_special=()))

    def metadata(self) -> dict[str, Any]:
        return {
            "name": "tiktoken",
            "version": self._version,
            "encoding": self._encoding_name,
            "exact_for_encoding": True,
            "exact_for_client_model": False,
        }


TiktokenCounter = TokenCounter
