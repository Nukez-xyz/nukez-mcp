"""nukez-mcp — Python client for the Nukez MCP server."""

from .client import (
    DEFAULT_ENDPOINT,
    PROTOCOL_VERSION,
    NukezMCP,
    NukezMCPError,
)

__version__ = "0.1.0"

__all__ = [
    "NukezMCP",
    "NukezMCPError",
    "DEFAULT_ENDPOINT",
    "PROTOCOL_VERSION",
    "__version__",
]
