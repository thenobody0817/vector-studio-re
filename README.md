# vector-studio-re

Reverse engineering of **Vector Studio** 0.1.11 (`@tenzen/vector-studio`), plus a
clean-room, standard-library-only client for the automation protocol the app
exposes to agents.

Nothing about Vector Studio's source is redistributed here. What is published is
the *protocol* (recovered from a shipped bundle), the tooling that recovers it,
and an independent implementation of the client side.

```
docs/protocol.md        wire protocol: endpoints, auth, envelope, errors, idempotency
docs/operations.md      the 16 operations and their schemas
docs/licensing.md       entitlement model (editions, gated features, native service)
docs/appimage-layout.md what is inside the AppImage, module by module
docs/operations.json    the capability catalog dumped from a live instance

tools/extract_asar.py   dependency-free asar reader/writer
tools/split_bundle.py   split the electron bundle back into its original modules
tools/re_context.py     find a symbol inside a minified bundle
tools/inspect_appimage.sh  reproduce the whole pipeline

client/vector_client.py     RPC client (capabilities, describe, session, edits, render)
client/vector_mcp_server.py MCP stdio bridge exposing `vector` and `vector_preview`

tests/test_client.py     protocol tests against a fake broker
tests/e2e_live.py        end-to-end test against a running Vector Studio
```

## The short version

Vector Studio is an Electron app for offline vector illustration. When
automation is enabled it starts a loopback HTTP broker that speaks a small
versioned JSON protocol:

```
POST http://127.0.0.1:<port>/api/v1/automation/rpc
Authorization: Bearer <64 hex chars from ~/.vector-studio/automation/credential>
{"version":1,"id":"req-1","operation":"shape.create","documentId":"…","expectedRevision":12,
 "params":{"kind":"rectangle","arguments":{…}}}
```

The same surface is exposed to agents as an MCP server over stdio with two
tools: `vector` (generic dispatcher) and `vector_preview` (rasterised PNG).

The port, the pid and the bearer secret are written to
`~/.vector-studio/automation/`. That is the whole integration surface - no
network calls, no accounts, no telemetry.

## Quick start

```bash
# 1. start Vector Studio with automation on
Vector-Studio-0.1.11-linux-x64.AppImage --automation

# 2. ask the app what it can do
python3 client/vector_client.py capabilities
python3 client/vector_client.py session-list
python3 client/vector_client.py describe shape.create

# 3. or wire it into an MCP host
python3 client/vector_mcp_server.py     # speaks MCP on stdin/stdout
```

Open-code style registration:

```jsonc
{
  "mcp": {
    "servers": {
      "vector": { "type": "local", "command": ["python3", "/path/to/vector-studio-re/client/vector_mcp_server.py"] }
    }
  }
}
```

## Verifying

```bash
python3 -m unittest discover -s tests   # offline protocol tests
python3 tests/e2e_live.py                # needs a running Vector Studio
```

`tests/e2e_live.py` was used to confirm the recovered protocol against the real
application: `capabilities` (16 operations), `describe`, `session.list`, the
`UNKNOWN_OPERATION` error path, and a full MCP handshake plus `tools/list` and
`tools/call`.

## How it was recovered

1. `--appimage-extract` unpacked the AppImage.
2. `tools/extract_asar.py` pulled `resources/app.asar` apart (no npm needed).
3. `tools/split_bundle.py` noticed that the shipped bundle keeps the original
   TypeScript modules inline (`// electron/automation.ts`, …) and split the
   14 MB bundle into 320 modules.
4. The broker, the auth scheme, the request ledger and the entitlement model
   were read out of those modules.
5. Every claim was checked against a live instance started with
   `--automation --ozone-platform=headless`.

## Legal

Vector Studio is a commercial product of Tenzen. This repository documents an
interoperable protocol and ships an independent client. It contains no
Tenzen source code, no assets and no licence keys. The AppImage itself is not
redistributed here - only the extraction and analysis tooling is.

## License

MIT - see [LICENSE](LICENSE).
