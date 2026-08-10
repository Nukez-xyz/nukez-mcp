"""Offline unit tests for the NukezMCP client (no network access)."""

import json

import httpx
import pytest

from nukez_mcp import NukezMCP, NukezMCPError, PROTOCOL_VERSION


def make_client(handler):
    return NukezMCP(transport=httpx.MockTransport(handler))


def json_rpc_result(request, result):
    body = json.loads(request.content)
    return httpx.Response(200, json={"jsonrpc": "2.0", "id": body["id"], "result": result})


def test_connect_parses_initialize_result():
    def handler(request):
        body = json.loads(request.content)
        assert body["method"] == "initialize"
        assert body["params"]["protocolVersion"] == PROTOCOL_VERSION
        return json_rpc_result(request, {
            "protocolVersion": PROTOCOL_VERSION,
            "serverInfo": {"name": "nukez", "version": "1.2.0"},
        })

    with make_client(handler) as mcp:
        assert not mcp.connected
        info = mcp.connect()
        assert mcp.connected
        assert info["serverInfo"]["name"] == "nukez"
        assert mcp.server_info == {"name": "nukez", "version": "1.2.0"}
        assert mcp.protocol_version == PROTOCOL_VERSION


def test_rpc_parses_event_stream_body():
    payload = {"jsonrpc": "2.0", "id": 1, "result": {"tools": [{"name": "nukez_status"}]}}
    sse = f"event: message\ndata: {json.dumps(payload)}\n\n"

    def handler(request):
        return httpx.Response(
            200, text=sse, headers={"content-type": "text/event-stream"}
        )

    with make_client(handler) as mcp:
        tools = mcp.list_tools()
        assert tools == [{"name": "nukez_status"}]


def test_rpc_error_raises():
    def handler(request):
        body = json.loads(request.content)
        return httpx.Response(200, json={
            "jsonrpc": "2.0", "id": body["id"],
            "error": {"code": -32601, "message": "method not found"},
        })

    with make_client(handler) as mcp:
        with pytest.raises(NukezMCPError) as exc:
            mcp.rpc("nope")
        assert exc.value.code == -32601


def test_call_tool_unwraps_json_text_content():
    def handler(request):
        body = json.loads(request.content)
        assert body["method"] == "tools/call"
        assert body["params"]["name"] == "nukez_status"
        assert body["params"]["arguments"] == {"receipt_id": "abc"}
        return json_rpc_result(request, {
            "content": [{"type": "text", "text": json.dumps({"ok": True, "stage": "active"})}],
        })

    with make_client(handler) as mcp:
        out = mcp.call_tool("nukez_status", {"receipt_id": "abc"})
        assert out == {"ok": True, "stage": "active"}


def test_call_tool_returns_plain_text_verbatim():
    def handler(request):
        return json_rpc_result(request, {
            "content": [{"type": "text", "text": "not json"}],
        })

    with make_client(handler) as mcp:
        assert mcp.call_tool("nukez_status") == "not json"


def test_call_tool_is_error_raises():
    def handler(request):
        return json_rpc_result(request, {
            "isError": True,
            "content": [{"type": "text", "text": "boom"}],
        })

    with make_client(handler) as mcp:
        with pytest.raises(NukezMCPError, match="boom"):
            mcp.call_tool("nukez_verify")


def test_sse_skips_non_json_data_lines():
    payload = {"jsonrpc": "2.0", "id": 1, "result": {"tools": []}}
    sse = f"data: ping\n\ndata: 42\n\nevent: message\ndata: {json.dumps(payload)}\n\n"

    def handler(request):
        return httpx.Response(
            200, text=sse, headers={"content-type": "text/event-stream"}
        )

    with make_client(handler) as mcp:
        assert mcp.list_tools() == []


def test_version_is_single_sourced():
    import re
    from pathlib import Path

    import nukez_mcp

    pyproject = Path(__file__).resolve().parents[1] / "pyproject.toml"
    match = re.search(r'^version = "(.+)"$', pyproject.read_text(), re.MULTILINE)
    assert match, "version field missing from pyproject.toml"
    assert match.group(1) == nukez_mcp.__version__

    sent = {}

    def handler(request):
        body = json.loads(request.content)
        sent.update(body["params"]["clientInfo"])
        return json_rpc_result(request, {
            "protocolVersion": PROTOCOL_VERSION,
            "serverInfo": {"name": "nukez", "version": "1.3.0"},
        })

    with make_client(handler) as mcp:
        mcp.connect()
    assert sent["version"] == nukez_mcp.__version__
