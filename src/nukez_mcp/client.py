"""HTTP client for the Nukez MCP server.

The Nukez MCP is a streamable HTTP JSON-RPC server. It wraps the Nukez
gateway but holds no server-side wallet or signing key: clients execute
payments externally, sign operation envelopes locally, and pass those
envelopes through MCP tool arguments.

This module speaks the transport layer only. Envelope signing and payment
execution are deliberately out of scope — see https://nukez.xyz/docs/mcp
for the canonical client-side signing and payment helpers.
"""

from __future__ import annotations

import json
from typing import Any, Optional

import httpx

from ._version import __version__

DEFAULT_ENDPOINT = "https://mcp.nukez.xyz/mcp"
PROTOCOL_VERSION = "2025-03-26"

_HEADERS = {
    "Content-Type": "application/json",
    "Accept": "application/json, text/event-stream",
}


class NukezMCPError(RuntimeError):
    """A JSON-RPC error or tool-level failure returned by the server."""

    def __init__(self, message: str, *, code: Optional[int] = None, data: Any = None):
        super().__init__(message)
        self.code = code
        self.data = data


class NukezMCP:
    """Client for the Nukez MCP server.

    Usage::

        from nukez_mcp import NukezMCP

        with NukezMCP() as mcp:
            info = mcp.connect()
            tools = mcp.list_tools()
            status = mcp.call_tool("nukez_status")

    The client is synchronous and stateless between calls: each JSON-RPC
    request is an independent POST to the endpoint, matching the server's
    streamable HTTP transport. Responses may arrive as plain JSON or as a
    text/event-stream body; both are handled transparently.
    """

    def __init__(
        self,
        endpoint: str = DEFAULT_ENDPOINT,
        *,
        timeout: float = 120.0,
        client_name: str = "nukez-mcp",
        client_version: str = __version__,
        transport: Optional[httpx.BaseTransport] = None,
    ):
        self.endpoint = endpoint
        self._client_info = {"name": client_name, "version": client_version}
        self._http = httpx.Client(timeout=timeout, transport=transport)
        self._req_id = 0
        self.server_info: Optional[dict] = None
        self.protocol_version: Optional[str] = None

    # ── Connection ────────────────────────────────────────────────────

    def connect(self) -> dict:
        """Perform the MCP ``initialize`` handshake.

        Returns the full initialize result and caches ``server_info`` and
        ``protocol_version`` on the client.
        """
        result = self.rpc(
            "initialize",
            {
                "protocolVersion": PROTOCOL_VERSION,
                "capabilities": {},
                "clientInfo": self._client_info,
            },
        )
        self.server_info = result.get("serverInfo")
        self.protocol_version = result.get("protocolVersion")
        return result

    @property
    def connected(self) -> bool:
        return self.server_info is not None

    # ── JSON-RPC transport ────────────────────────────────────────────

    def rpc(self, method: str, params: Optional[dict] = None) -> Any:
        """Send one JSON-RPC request and return its ``result``.

        Raises :class:`NukezMCPError` if the server returns a JSON-RPC
        error object.
        """
        self._req_id += 1
        payload: dict[str, Any] = {
            "jsonrpc": "2.0",
            "id": self._req_id,
            "method": method,
        }
        if params:
            payload["params"] = params

        resp = self._http.post(self.endpoint, json=payload, headers=_HEADERS)
        resp.raise_for_status()

        body = self._parse_body(resp)
        if body is None:
            raise NukezMCPError(f"empty or unparseable response for {method!r}")
        if "error" in body:
            err = body["error"] or {}
            raise NukezMCPError(
                str(err.get("message", "unknown JSON-RPC error")),
                code=err.get("code"),
                data=err.get("data"),
            )
        return body.get("result")

    @staticmethod
    def _parse_body(resp: httpx.Response) -> Optional[dict]:
        """Parse a plain-JSON or text/event-stream response body.

        For event streams, the first ``data:`` line carrying a ``result``
        or ``error`` member wins.
        """
        content_type = resp.headers.get("content-type", "")
        if "text/event-stream" in content_type:
            for line in resp.text.splitlines():
                if line.startswith("data: "):
                    try:
                        data = json.loads(line[len("data: "):])
                    except json.JSONDecodeError:
                        continue  # keepalive/ping frames are not JSON-RPC payloads
                    if isinstance(data, dict) and ("result" in data or "error" in data):
                        return data
            return None
        try:
            return resp.json()
        except json.JSONDecodeError:
            return None

    # ── Tools ─────────────────────────────────────────────────────────

    def list_tools(self) -> list[dict]:
        """Return the server's tool definitions (``tools/list``)."""
        result = self.rpc("tools/list")
        return result.get("tools", []) if result else []

    def call_tool(self, name: str, arguments: Optional[dict] = None) -> Any:
        """Call an MCP tool and return its decoded payload.

        Nukez tools return a single JSON document as text content; this
        method decodes it to a dict. Non-JSON text is returned verbatim,
        and any other result shape is returned unmodified.

        Raises :class:`NukezMCPError` if the server marks the call result
        as an error (``isError``).
        """
        params: dict[str, Any] = {"name": name}
        if arguments:
            params["arguments"] = arguments
        result = self.rpc("tools/call", params)

        if isinstance(result, dict):
            texts = [
                c.get("text", "")
                for c in result.get("content", [])
                if c.get("type") == "text"
            ]
            if result.get("isError"):
                raise NukezMCPError(
                    texts[0] if texts else f"tool {name!r} returned an error"
                )
            if texts:
                try:
                    return json.loads(texts[0])
                except json.JSONDecodeError:
                    return texts[0]
        return result

    # ── Lifecycle ─────────────────────────────────────────────────────

    def close(self) -> None:
        self._http.close()

    def __enter__(self) -> "NukezMCP":
        return self

    def __exit__(self, *exc_info: Any) -> None:
        self.close()
