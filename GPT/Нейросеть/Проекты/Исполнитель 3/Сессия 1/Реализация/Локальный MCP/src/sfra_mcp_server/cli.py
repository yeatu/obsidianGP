"""Command-line entry point for the local SFRA stdio server."""
from __future__ import annotations

import sys

from .composition import CompositionError
from .config import ConfigurationError, ServerConfig
from .server import build_runtime, run_stdio


def main() -> int:
    try:
        config = ServerConfig.from_env()
        runtime = build_runtime(config)
    except (ConfigurationError, CompositionError) as exc:
        print(f"SFRA MCP startup error: {exc}", file=sys.stderr)
        return 2

    run_stdio(runtime)
    return 0
