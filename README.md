# nukez-mcp

Python client for the **Nukez MCP server** — agent-native persistent storage
with cryptographic verification on Solana.

The Nukez MCP is a streamable HTTP JSON-RPC server that wraps the Nukez
gateway. It is **keyless**: the server never holds a wallet or signing key.
Clients execute payments externally, sign Ed25519 operation envelopes
locally, and pass those envelopes through MCP tool arguments.

This package provides a simple class around an HTTP library with a method
for connecting to the server, listing its tools, and calling them.

## Install

```bash
pip install nukez-mcp
```

### Minimum installer versions

Install (or `uvx` / `pipx run`) this package only with pip >= 26.2.2,
uv/uvx >= 0.13.4, pipx >= 1.18.4, or npm/npx on Node >= 22.23.4 / 24.22.1 /
26.12.1. Older installers bundle a CA store that still trusts the compromised
eMudhra/emSign intermediate CAs (2026-10-22) and can be served a tampered
package even after the operating system has revoked that chain; the client
itself requires `certifi >= 2026.10.19` at runtime for its HTTPS calls to the
MCP server.

## Quickstart

```python
from nukez_mcp import NukezMCP

with NukezMCP() as mcp:
    info = mcp.connect()
    print(info["serverInfo"])          # server name and version

    tools = mcp.list_tools()
    print(f"{len(tools)} tools registered")

    status = mcp.call_tool("nukez_status")
    print(status["capabilities"]["payment_rails"])
```

The default endpoint is the production server:

```
https://mcp.nukez.xyz/mcp
```

Pass a different `endpoint=` to the constructor to target another
deployment.

## The tool surface

The production server registers 15 tools:

| Group | Tools |
|-------|-------|
| Payment & setup | `nukez_quote`, `nukez_pay`, `nukez_provision`, `nukez_setup` |
| Files | `nukez_create_file`, `nukez_store`, `nukez_confirm`, `nukez_upload_chunk`, `nukez_retrieve`, `nukez_delete` |
| Proof & freshness | `nukez_status`, `nukez_verify`, `nukez_recompute_verify` |
| Memory | `nukez_remember`, `nukez_recall` |

The canonical flow is `nukez_quote` → external chain transfer → `nukez_pay`
→ `nukez_provision`, after which mutating and payer-authorized operations —
store, confirm, delete, remember, attest push, recompute-verify — require
client-signed envelopes. Reads such as retrieve, recall, status, and
structural verify need only the `receipt_id`.

## Signed envelopes and payments

Envelope signing and payment execution are deliberately **not** part of this
package: they involve your local keypair and are documented, with runnable
helpers, in the canonical guides:

- <https://nukez.xyz/docs/mcp> — production model and connection details
- <https://nukez.xyz/docs/mcp/examples> — envelope signing (`pynacl` +
  `base58`) and Solana transfer helpers (`solders`)
- <https://nukez.xyz/docs/mcp/tools> — full tool reference

A signed envelope is passed straight through a tool's `envelope` argument:

```python
env = {...}  # built and signed locally — see docs/mcp/examples

files = mcp.call_tool("nukez_retrieve", {
    "receipt_id": receipt_id,
    "envelope": env,
})
```

Two exceptions to the one-envelope pattern: `nukez_remember` takes a
**list of two** signed envelopes (one for the memory record file, one for
the index), and `nukez_quote` / `nukez_pay` / `nukez_upload_chunk` take no
envelope at all.

## Worked example: two-phase on-chain attestation

Anchoring an attestation is a two-phase flow — the server is keyless, so the
first call returns `action_required="sign_envelopes"` with an envelope spec
(note the `query` field, which the signed envelope JSON must carry verbatim),
and the second call anchors on-chain. The gateway also auto-reattests after
every file mutation, so an explicit `push=True` is only needed when you want
an immediate, inline on-chain anchor:

```python
v1 = mcp.call_tool("nukez_verify", {"receipt_id": receipt_id, "push": True})
spec = v1["envelopes_needed"][0]

attest_env = build_envelope(          # your local signer — see docs/mcp/examples
    receipt_id, spec["method"], spec["path"],
    ops=spec["ops"], body=spec["body"], query=spec["query"],
)

v2 = mcp.call_tool("nukez_verify", {
    "receipt_id": receipt_id, "push": True, "envelope": attest_env,
})
assert v2["attestation"]["push_ok"]   # anchored: tx_signature is on Solana
```

## Reference demonstration: Trust Verification

The canonical end-to-end usage example is the **Trust Verification demo** — a
live, agent-driven walkthrough that connects to the production Nukez MCP
server, provisions storage with a real BETA-token x402 payment, stores and
encrypts artifacts through signed MCP operations, survives a tamper attempt,
and verifies everything on Solana mainnet across 10 preset cues, including:

1. Agent surface online → **connect to the Nukez protocol via MCP**
2. Grant local wallet access (a discrete consent moment — the server never
   holds keys)
3. Procure user-owned storage on Solana mainnet (BETA-paid x402 quote)
4. Draft a real output artifact
5. Store artifacts through signed Nukez MCP operations
6. Attack: an adversary attempts to tamper with the record
7. Verify: the tamper is detected against the on-chain attestation

Every request in that demo travels the same JSON-RPC surface this package
wraps: `initialize` → `tools/call` with envelope passthrough, exactly as in
the Quickstart above. The demo's signing/payment helpers are packaged from
the runnable examples at <https://nukez.xyz/docs/mcp/examples>.

## Errors

JSON-RPC errors and tool-level failures raise `nukez_mcp.NukezMCPError`,
carrying `code` and `data` when the server provides them.

## License

MIT
