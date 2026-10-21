# Operation catalog

16 operations are exposed by the version-1 broker. `operations.json` next to this
file is the verbatim catalog dumped from a live instance
(`vector capabilities`), including the JSON Schema of every parameter.

## Discovery

| Operation | Purpose |
|---|---|
| `capabilities` | list operations; `params.query` filters (case-insensitive substring over the JSON) |
| `describe` | full schema of one operation: `params.operation` |

## Session

| Operation | Notes |
|---|---|
| `session.list` | returns `{"sessions": [...], "activeId": <id|null>, "busy": <bool>}` |
| `session.show` | focuses the app window (`{"shown": true}`) |

## Document

| Operation | Revision-guarded | Notes |
|---|---|---|
| `inspect` | no | active document, selection and Illustrator compatibility |
| `render` | yes (`documentId` + `expectedRevision`) | returns `{base64, mimeType:"image/png", documentId, revision}`; `params.edge` = 64..2048, default 1536 |
| `selection.set` | yes | `params.ids` - array of object ids, max 1000 |
| `shape.create` | yes | see the shape table below |
| `undo` | yes | one artwork edit back |
| `redo` | yes | one artwork edit forward |

### `shape.create`

`params` is a discriminated union on `kind`; every shape carries a `paint`
object (`fill`, `stroke`, `strokeWidth` - `fill`/`stroke` may be `null`).

| `kind` | arguments |
|---|---|
| `rectangle` | `x`, `y`, `width` (>0), `height` (>0) |
| `ellipse` | `x`, `y`, `width` (>0), `height` (>0) |
| `line` | `x1`, `y1`, `x2`, `y2` |
| `polygon` | `x`, `y`, `radius` (>0), `sides` (3..1000), `rotationRadians` |
| `star` | `x`, `y`, `radius1` (>0), `radius2` (>0), `points` (2..500), `rotationRadians` |

Coordinates are document points, rotations are radians.

## Integrations (agent connections)

| Operation | Params |
|---|---|
| `integrations.list` | `projectPath` (optional) |
| `integrations.install` | `agent` (required), `projectPath`, `custom` |
| `integrations.remove` | `agent` (required), `projectPath`, `custom` |
| `integrations.test` | `agent` (required), `projectPath`, `custom` |

Known agent ids (from the shipped integration manager): `claude-code`, `codex`,
`cursor`, `vscode`, `gemini`, `opencode`, `copilot`, `pi`, `openclaw`,
`hermes`, `mcporter`, plus `custom`.

Each agent maps to a config file and an entry path:

| Agent | Config | Entry |
|---|---|---|
| `claude-code` | `~/.claude.json` or `<project>/.mcp.json` | `mcpServers.vector` |
| `codex` | `~/.codex/config.toml` | `mcp_servers.vector` |
| `cursor` | `~/.cursor/mcp.json` | `mcpServers.vector` |
| `vscode` | `~/.config/Code/User/mcp.json` or `<project>/.vscode/mcp.json` | `servers.vector` |
| `gemini` | `~/.gemini/settings.json` | `mcpServers.vector` |
| `opencode` | `~/.config/opencode/opencode.json` or `<project>/opencode.json` | `mcp.servers.vector` |
| `copilot` | `~/.copilot/mcp-config.json` or `<project>/.github/skills` | `mcpServers.vector` |
| `hermes` | `~/.hermes/config.yaml` | `mcp_servers.vector` |
| `mcporter` | `~/.mcporter/mcporter.json` | `mcpServers.vector` |

The registered entry launches the bundled CLI as an MCP stdio server.

## Skills (workflow packs)

| Operation | Params |
|---|---|
| `skills.list` | - |
| `skills.import` | `path` (required) |
| `skills.export` | `name`, `path` (both required) |
| `skills.remove` | `name` |

The app ships one pack: `skills/automation/vector-artwork/` with
`manifest.json` (`{"version":"1.0.0","protocolVersion":1,"requiredCapabilities":["inspect","shape.create","render"]}`)
and a `SKILL.md` that tells an agent how to drive the protocol safely.
