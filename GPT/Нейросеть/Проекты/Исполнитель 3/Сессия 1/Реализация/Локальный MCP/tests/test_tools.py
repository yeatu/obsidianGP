from __future__ import annotations

import inspect
from typing import get_type_hints

import pytest
from mcp.server.mcpserver.exceptions import ToolError

from sfra_mcp_server.tools import register_tool_slots


class RecordingServer:
    def __init__(self) -> None:
        self.tools = {}

    def tool(self, *, name: str, description: str):
        def register(function):
            self.tools[name] = {"description": description, "handler": function}
            return function
        return register


def test_registers_exactly_the_two_contract_tool_slots() -> None:
    server = RecordingServer()
    register_tool_slots(server)
    assert set(server.tools) == {"search_vault", "read_source"}
    search = server.tools["search_vault"]["handler"]
    read = server.tools["read_source"]["handler"]
    assert list(inspect.signature(search).parameters) == [
        "query", "task", "entities", "facets", "zones",
        "budget_tokens", "known", "focus",
    ]
    assert list(inspect.signature(read).parameters) == [
        "node_id", "expected_hash", "scope", "snapshot", "budget_tokens",
    ]
    assert get_type_hints(read)["scope"].__args__ == (
        "node", "parent", "neighbors", "document",
    )


def test_tool_slots_fail_closed_until_child_handlers_are_implemented() -> None:
    server = RecordingServer()
    register_tool_slots(server)
    with pytest.raises(ToolError, match="Issue #39"):
        server.tools["search_vault"]["handler"]("fixture query")
    with pytest.raises(ToolError, match="Issue #40"):
        server.tools["read_source"]["handler"](
            "node_fixture", "sha256:" + "a" * 64, "node",
            {
                "vault_commit_sha": "a" * 40,
                "sidecar_commit_sha": "b" * 40,
                "manifest_sha256": "sha256:" + "c" * 64,
            },
        )
