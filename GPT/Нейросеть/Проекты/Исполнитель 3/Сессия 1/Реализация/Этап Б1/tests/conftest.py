from __future__ import annotations

import hashlib
import json

import pytest


class WordCounter:
    """Deterministic test double; production defaults to tiktoken."""

    def count(self, text: str) -> int:
        return len(text.split())

    def metadata(self):
        return {
            "name": "word-counter-test-double",
            "version": "1",
            "encoding": "whitespace",
            "exact_for_encoding": True,
            "exact_for_client_model": False,
        }


@pytest.fixture
def counter():
    return WordCounter()


@pytest.fixture
def builder(counter):
    from sfra_context_builder import ContextBuilder
    return ContextBuilder(counter)


def make_candidate(node_id, text, **extra):
    digest = "sha256:" + hashlib.sha256(text.encode("utf-8")).hexdigest()
    candidate = {
        "node_id": node_id,
        "source_path": f"fixtures/{node_id}.md",
        "heading_path": ["Section"],
        "line_start": 1,
        "line_end": 1,
        "content_hash": digest,
        "raw_text": text,
        "match_type": "exact",
        "relevance": {"tier": 3, "bm25": -1.0},
        "match_reasons": [],
        "signals": {},
        "matched_focus_ids": [],
        "preservation": "normal",
        "required_with": [],
        "parent_context_required": False,
        "index_generation": 1,
        "document_hash": "sha256:" + ("a" * 64),
    }
    candidate.update(extra)
    return candidate


def make_batch(*candidates, complete=True, truncated=False):
    return {
        "complete": complete,
        "inspected_count": len(candidates),
        "truncated_by_limit": truncated,
        "candidates": list(candidates),
    }


def make_request(**extra):
    request = {"query": "test query", "budget_tokens": 1000, "known": [], "focus": []}
    request.update(extra)
    return request
