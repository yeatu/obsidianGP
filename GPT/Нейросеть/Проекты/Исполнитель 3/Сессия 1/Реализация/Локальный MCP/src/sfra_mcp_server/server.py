"""Composition root for the local MCP stdio process."""
from __future__ import annotations

from dataclasses import dataclass

from mcp.server import MCPServer

from .composition import ApplicationServices, build_application_services
from .config import ServerConfig
from .tools import register_tool_slots


@dataclass(frozen=True, slots=True)
class ServerRuntime:
    """Validated configuration, composed application services and MCP server."""

    config: ServerConfig
    services: ApplicationServices
    server: MCPServer


def build_runtime(config: ServerConfig) -> ServerRuntime:
    """Build the verified E1/E2/E3 graph and register only agreed tool slots."""
    if not isinstance(config, ServerConfig):
        raise TypeError("config must be a validated ServerConfig")

    # Bind a single verified snapshot before any tool is exposed.
    services = build_application_services(config)
    server = MCPServer(
        "SFRA Local Retrieval",
        instructions=(
            "Local read-only SFRA retrieval server. "
            "The search_vault and read_source contracts are registered, "
            "but their operation handlers are installed by Issues #39 and #40."
        ),
    )
    register_tool_slots(server)
    return ServerRuntime(config=config, services=services, server=server)


def run_stdio(runtime: ServerRuntime) -> None:
    """Run only the local stdio transport; callers cannot select a remote transport."""
    if not isinstance(runtime, ServerRuntime):
        raise TypeError("runtime must be a validated ServerRuntime")
    runtime.server.run(transport="stdio")
