"""nukez-mcp — Python client for the Nukez MCP server."""

from ._version import __version__
from .client import (
    DEFAULT_ENDPOINT,
    PROTOCOL_VERSION,
    NukezMCP,
    NukezMCPError,
)

__all__ = [
    "NukezMCP",
    "NukezMCPError",
    "DEFAULT_ENDPOINT",
    "PROTOCOL_VERSION",
    "__version__",
]
