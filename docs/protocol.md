# Vector Studio automation protocol (version 1)

Reverse engineered from the shipped Linux AppImage
`Vector-Studio-0.1.11-linux-x64.AppImage` (Electron 44.5.1, Chrome 152.0.7977.130).

Everything below was read out of the shipped bundle (`dist-electron/electron/main.js`,
which keeps the original TypeScript sources inline) and then verified live against a
running instance - see `tests/e2e_live.py`.

## 1. Transport

The app runs a loopback HTTP broker. It is started when automation is enabled
(Settings -> Integrations) or when the app is launched with `--automation`.

| | |
|---|---|
| Base URL | `http://127.0.0.1:<port>` |
| RPC endpoint | `POST /api/v1/automation/rpc` |
| Event stream | `GET /api/v1/automation/events` |
| Bind address | `127.0.0.1` only, ephemeral port |
| Request timeout | 30 s (`server.requestTimeout`), 10 s for headers |
| Max request body | 1 MiB (413 `Request exceeds 1 MiB.`) |
| Response | `application/json`, `Connection: close`, `Cache-Control: no-store` |

Requests are serialised: the broker chains every call onto one promise tail, so
one document mutation is never interleaved with another.

## 2. Locating the broker

The automation home directory resolves in this order:

1. `$VECTOR_STUDIO_AUTOMATION_HOME`
2. `$VECTOR_STUDIO_USER_DATA/automation`
3. `~/.vector-studio/automation` (packaged builds)

| File | Mode | Content |
|---|---|---|
| `runtime.json` | 0600 | `{"version":1,"product":"vector","port":45199,"pid":603809,"instanceId":"<uuid>"}` |
| `credential` | 0600 | 64 hex chars - the shared secret |
| `credentials/<id>` | 0600 | 64 hex chars - a per-integration secret |
| `enabled` | 0600 | `1` - automation is on |
| `installation.json` | 0600 | CLI installation receipt |
| `requests/` | 0700 | idempotency ledger (see §6) |

## 3. Authentication

Every request carries `Authorization: Bearer <token>`.

* Shared token: the contents of `credential` (64 hex chars).
* Scoped token: `<integration-id>.<secret>` where `<secret>` is the contents of
  `credentials/<integration-id>`. The CLI picks the id from
  `$VECTOR_STUDIO_INTEGRATION_ID`.

The broker rejects a request when **any** of these is true (answer `401 {"error":"Unauthorized"}`):

* an `Origin` header is present (blocks browser-based CSRF),
* the `Host` header is not exactly `127.0.0.1:<port>`,
* the bearer token does not match the expected secret (constant-time compare).

## 4. Request envelope

```jsonc
{
  "version": 1,                 // must be 1
  "id": "req-1",                // client-chosen, <= 200 chars
  "operation": "shape.create",  // see operations.md
  "params": { },                // optional, object only
  "documentId": "doc-1",        // optional
  "sessionId": "sess-1",        // optional
  "expectedRevision": 12        // optional, optimistic concurrency
}
```

Any other top-level key is rejected with `INVALID_INPUT`.
`id` is the idempotency key: reusing it with different arguments yields
`ID_CONFLICT`.

## 5. Response envelope

```jsonc
{ "version": 1, "id": "req-1", "ok": true,  "result": { } }
{ "version": 1, "id": "req-1", "ok": false, "error": { "code": "…", "message": "…" } }
```

Error codes observed in the shipped bundle:

| Code | Meaning |
|---|---|
| `INVALID_INPUT` | envelope or parameter validation failed |
| `UNKNOWN_OPERATION` | operation id not in the capability catalog |
| `HOST_NOT_READY` | renderer/editor not ready yet |
| `OUTCOME_UNKNOWN` | edit may have committed - inspect before retrying |
| `ID_CONFLICT` | request id reused with different arguments |
| `OPERATION_FAILED` | default for anything else |
| `LICENSE_REQUIRED` / `NATIVE_UNAVAILABLE` | entitlement gating (see licensing.md) |

## 6. Idempotency

Operations flagged `revision: true` in the capability catalog (`selection.set`,
`shape.create`, `undo`, `redo`) are journalled:

1. The broker hashes the canonical (key-sorted) request with SHA-256.
2. If the ledger already holds that id with a different hash -> `ID_CONFLICT`.
3. If the ledger holds that id with the same hash -> the stored response is
   replayed (no second edit).

The ledger lives in `requests/` inside the automation home, so it survives an
app restart and protects against a client retrying after a timeout.

## 7. Optimistic concurrency

`expectedRevision` is compared against the document revision inside the
renderer. A stale value is rejected; the caller is expected to re-`inspect`
and retry with the fresh revision.

## 8. Event stream

`GET /api/v1/automation/events` is a long-lived `HTTP/1.0` response with
`Connection: close` that streams newline-delimited JSON events (document
revisions, session changes). The shipped CLI subscribes to it to keep its
`--revision` value fresh.

## 9. MCP bridge

The bundled CLI (`resources/cli/vector mcp`) speaks MCP over stdio using
newline-delimited JSON-RPC 2.0. Handshake (verified live):

```jsonc
// -> initialize
{ "jsonrpc": "2.0", "id": 1, "method": "initialize",
  "params": { "protocolVersion": "2025-11-25", "capabilities": {}, "clientInfo": {…} } }
// <- result
{ "jsonrpc": "2.0", "id": 1, "result": {
    "protocolVersion": "2025-11-25",
    "capabilities": { "tools": {} },
    "serverInfo": { "name": "vector", "version": "0.1.11" },
    "instructions": "…" } }
```

The server exposes exactly two tools:

| Tool | Required arguments | Optional arguments |
|---|---|---|
| `vector` | `operation` | `params`, `documentId`, `sessionId`, `expectedRevision`, `requestId` |
| `vector_preview` | `documentId` | `sessionId`, `expectedRevision`, `params.edge` |

`vector_preview` returns an MCP image content block
(`type: "image"`, `data: <base64 PNG>`, `mimeType: "image/png"`); the broker
rasterises the SVG with sharp (`edge` between 64 and 2048, default 1536).

`client/vector_mcp_server.py` in this repository reimplements that bridge with
the Python standard library only.
