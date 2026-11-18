from __future__ import annotations

import asyncio
from typing import Any

import pytest
from mcp.server import MCPServer
from mcp.server.context import ServerRequestContext
from mcp.server.mcpserver.context import Context
from mcp.server.mcpserver.exceptions import ToolError

from sfra_mcp_server.tools import register_tool_slots


def _server() -> MCPServer:
    server = MCPServer("SFRA schema fixture")
    register_tool_slots(server)
    return server


def _listed_schemas(server: MCPServer) -> dict[str, dict[str, Any]]:
    # This is the same MCPServer.list_tools() surface used by tools/list.
    tools = asyncio.run(server.list_tools())
    result: dict[str, dict[str, Any]] = {}
    for tool in tools:
        payload = tool.model_dump(by_alias=True)
        result[tool.name] = payload["inputSchema"]
    return result


def _invoke(server: MCPServer, name: str, arguments: dict[str, Any]) -> Any:
    request_context = ServerRequestContext(
        session=None,
        lifespan_context={},
        protocol_version="2025-03-26",
        method="tools/call",
        params={"name": name, "arguments": arguments},
        request_id="fixture-request",
    )
    context = Context(request_context=request_context, mcp_server=server)
    return asyncio.run(server.call_tool(name, arguments, context))


def _resolve(schema: dict[str, Any], value: dict[str, Any]) -> dict[str, Any]:
    ref = value.get("$ref")
    if not isinstance(ref, str) or not ref.startswith("#/$defs/"):
        return value
    return schema["$defs"][ref.rsplit("/", 1)[-1]]


def _assert_positive_integer_or_null(schema: dict[str, Any]) -> None:
    branches = schema.get("anyOf", schema.get("oneOf", [schema]))
    integer_branch = next(branch for branch in branches if branch.get("type") == "integer")
    assert integer_branch["minimum"] == 1
    assert any(branch.get("type") == "null" for branch in branches)


def test_actual_mcp_tool_list_publishes_both_closed_contract_schemas() -> None:
    server = _server()
    schemas = _listed_schemas(server)

    assert set(schemas) == {"search_vault", "read_source"}

    search = schemas["search_vault"]
    assert search["type"] == "object"
    assert search["additionalProperties"] is False
    assert search["required"] == ["query"]
    assert search["properties"]["query"]["minLength"] == 1
    assert search["properties"]["budget_tokens"]["type"] == "integer"
    assert search["properties"]["budget_tokens"]["minimum"] == 1
    assert search["properties"]["budget_tokens"]["default"] == 3000

    for field in ("entities", "facets", "zones"):
        assert search["properties"][field]["items"]["minLength"] == 1

    known = _resolve(search, search["properties"]["known"]["items"])
    assert known["additionalProperties"] is False
    assert known["required"] == ["node_id", "content_hash"]
    assert known["properties"]["node_id"]["minLength"] == 1
    assert known["properties"]["content_hash"]["pattern"] == r"^sha256:[0-9a-fA-F]{64}$"

    focus_item = search["properties"]["focus"]["items"]
    focus_branches = focus_item.get("anyOf", focus_item.get("oneOf"))
    assert focus_branches is not None
    string_branch = next(branch for branch in focus_branches if branch.get("type") == "string")
    assert string_branch["minLength"] == 1
    aspect_ref = next(branch for branch in focus_branches if "$ref" in branch)
    aspect = _resolve(search, aspect_ref)
    assert aspect["additionalProperties"] is False
    assert aspect["required"] == ["id", "label"]
    assert aspect["properties"]["id"]["minLength"] == 1
    assert aspect["properties"]["label"]["minLength"] == 1
    for field in ("entities", "facets", "terms"):
        assert aspect["properties"][field]["items"]["minLength"] == 1
    assert aspect["properties"]["match_mode"]["enum"] == ["any", "all"]

    read = schemas["read_source"]
    assert read["type"] == "object"
    assert read["additionalProperties"] is False
    assert read["required"] == ["node_id", "expected_hash", "scope", "snapshot"]
    assert read["properties"]["node_id"]["minLength"] == 1
    assert read["properties"]["expected_hash"]["pattern"] == r"^sha256:[0-9a-f]{64}$"
    assert read["properties"]["scope"]["enum"] == ["node", "parent", "neighbors", "document"]
    _assert_positive_integer_or_null(read["properties"]["budget_tokens"])

    snapshot = _resolve(read, read["properties"]["snapshot"])
    assert snapshot["additionalProperties"] is False
    assert snapshot["required"] == [
        "vault_commit_sha", "sidecar_commit_sha", "manifest_sha256",
    ]
    assert snapshot["properties"]["vault_commit_sha"]["pattern"] == r"^[0-9a-f]{40}$"
    assert snapshot["properties"]["sidecar_commit_sha"]["pattern"] == r"^[0-9a-f]{40}$"
    assert snapshot["properties"]["manifest_sha256"]["pattern"] == r"^sha256:[0-9a-f]{64}$"
    assert "snapshot_id" not in snapshot["required"]


@pytest.mark.parametrize(
    "arguments",
    [
        {"query": ""},
        {"query": "fixture", "budget_tokens": 0},
        {"query": "fixture", "budget_tokens": True},
        {"query": "fixture", "entities": [""]},
        {"query": "fixture", "known": [{"node_id": "", "content_hash": "sha256:" + "a" * 64}]},
        {
            "query": "fixture",
            "known": [{"node_id": "node", "content_hash": "sha256:" + "a" * 64, "extra": "x"}],
        },
        {"query": "fixture", "focus": [""]},
        {"query": "fixture", "focus": [{"id": "x", "label": "", "extra": "x"}]},
        {"query": "fixture", "unsupported": "x"},
    ],
)
def test_search_rejects_invalid_or_unknown_arguments_before_handler_work(
    arguments: dict[str, Any],
) -> None:
    server = _server()
    with pytest.raises(ToolError):
        _invoke(server, "search_vault", arguments)


def test_search_valid_request_reaches_only_fail_closed_placeholder() -> None:
    server = _server()
    with pytest.raises(ToolError, match="Issue #39"):
        _invoke(server, "search_vault", {"query": "fixture"})


@pytest.mark.parametrize(
    "arguments",
    [
        {
            "node_id": "",
            "expected_hash": "sha256:" + "a" * 64,
            "scope": "node",
            "snapshot": {
                "vault_commit_sha": "a" * 40,
                "sidecar_commit_sha": "b" * 40,
                "manifest_sha256": "sha256:" + "c" * 64,
            },
        },
        {
            "node_id": "node",
            "expected_hash": "sha256:" + "A" * 64,
            "scope": "node",
            "snapshot": {
                "vault_commit_sha": "a" * 40,
                "sidecar_commit_sha": "b" * 40,
                "manifest_sha256": "sha256:" + "c" * 64,
            },
        },
        {
            "node_id": "node",
            "expected_hash": "sha256:" + "a" * 64,
            "scope": "node",
            "snapshot": {
                "vault_commit_sha": "A" * 40,
                "sidecar_commit_sha": "b" * 40,
                "manifest_sha256": "sha256:" + "c" * 64,
            },
        },
        {
            "node_id": "node",
            "expected_hash": "sha256:" + "a" * 64,
            "scope": "node",
            "snapshot": {
                "vault_commit_sha": "a" * 40,
                "sidecar_commit_sha": "b" * 40,
                "manifest_sha256": "sha256:" + "c" * 64,
                "unknown": "x",
            },
        },
        {
            "node_id": "node",
            "expected_hash": "sha256:" + "a" * 64,
            "scope": "node",
            "snapshot": {
                "vault_commit_sha": "a" * 40,
                "sidecar_commit_sha": "b" * 40,
                "manifest_sha256": "sha256:" + "c" * 64,
            },
            "budget_tokens": True,
        },
        {
            "node_id": "node",
            "expected_hash": "sha256:" + "a" * 64,
            "scope": "node",
            "snapshot": {
                "vault_commit_sha": "a" * 40,
                "sidecar_commit_sha": "b" * 40,
                "manifest_sha256": "sha256:" + "c" * 64,
            },
            "unsupported": "x",
        },
    ],
)
def test_read_source_rejects_invalid_or_unknown_arguments_before_handler_work(
    arguments: dict[str, Any],
) -> None:
    server = _server()
    with pytest.raises(ToolError):
        _invoke(server, "read_source", arguments)


def test_read_source_requires_snapshot_and_keeps_handler_disabled() -> None:
    server = _server()
    with pytest.raises(ToolError):
        _invoke(
            server,
            "read_source",
            {
                "node_id": "node",
                "expected_hash": "sha256:" + "a" * 64,
                "scope": "node",
            },
        )

    with pytest.raises(ToolError, match="Issue #40"):
        _invoke(
            server,
            "read_source",
            {
                "node_id": "node",
                "expected_hash": "sha256:" + "a" * 64,
                "scope": "node",
                "snapshot": {
                    "vault_commit_sha": "a" * 40,
                    "sidecar_commit_sha": "b" * 40,
                    "manifest_sha256": "sha256:" + "c" * 64,
                },
            },
        )
