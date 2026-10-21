#!/usr/bin/env python3
"""Open-source MCP bridge for Vector Studio.

Reimplements the two tools the shipped Vector Studio CLI exposes over MCP
(`vector` and `vector_preview`) against the local automation broker, using
nothing but the Python standard library.

Register it with any MCP host, e.g. opencode:

    {
      "mcp": {
        "servers": {
          "vector": { "type": "local", "command": ["python3", "vector_mcp_server.py"] }
        }
      }
    }

Protocol: newline-delimited JSON-RPC 2.0 on stdin/stdout (MCP stdio transport).
"""

from __future__ import annotations

import json
import sys
from typing import Any

from vector_client import VectorStudio, VectorStudioError

SERVER_NAME = "vector"
SERVER_VERSION = "1.0.0"
PROTOCOL_VERSION = "2025-11-25"

INSTRUCTIONS = (
    "Control Vector Studio. Start with operation capabilities (params.query narrows results), "
    "session.list, or describe (params.operation). Edits require documentId and "
    "expectedRevision. render returns an image. Discover supported operations with "
    "capabilities. Use the discovered schemas rather than guessing parameters."
)

TOOLS = [
    {
        "name": SERVER_NAME,
        "description": INSTRUCTIONS,
        "inputSchema": {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "operation": {"type": "string"},
                "params": {"type": "object"},
                "documentId": {"type": "string"},
                "sessionId": {"type": "string"},
                "expectedRevision": {"type": "integer"},
                "requestId": {"type": "string", "minLength": 1, "maxLength": 200},
            },
            "required": ["operation"],
        },
    },
    {
        "name": f"{SERVER_NAME}_preview",
        "description": "Preview vector artwork at a committed revision.",
        "inputSchema": {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "documentId": {"type": "string"},
                "sessionId": {"type": "string"},
                "expectedRevision": {"type": "integer"},
                "params": {"type": "object"},
            },
            "required": ["documentId"],
        },
    },
]


def _result(request_id: Any, result: Any) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": request_id, "result": result}


def _error(request_id: Any, code: int, message: str) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": request_id, "error": {"code": code, "message": message}}


def call_tool(client: VectorStudio, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    """Execute one tool and shape the reply as MCP tool content."""
    if name == SERVER_NAME:
        payload = client.rpc(
            arguments["operation"],
            arguments.get("params"),
            document_id=arguments.get("documentId"),
            session_id=arguments.get("sessionId"),
            expected_revision=arguments.get("expectedRevision"),
            request_id=arguments.get("requestId"),
        )
        return {
            "content": [{"type": "text", "text": json.dumps(payload, indent=2)}],
            "isError": False,
        }

    if name == f"{SERVER_NAME}_preview":
        payload = client.render(
            arguments["documentId"],
            arguments.get("expectedRevision", 0),
            (arguments.get("params") or {}).get("edge"),
        )
        return {
            "content": [
                {
                    "type": "image",
                    "data": payload["base64"],
                    "mimeType": payload.get("mimeType", "image/png"),
                }
            ],
            "isError": False,
        }

    raise VectorStudioError(f"unknown tool: {name}")


def handle(message: dict[str, Any], client: VectorStudio) -> dict[str, Any] | None:
    method = message.get("method")
    request_id = message.get("id")
    params = message.get("params") or {}

    if method == "initialize":
        return _result(
            request_id,
            {
                "protocolVersion": PROTOCOL_VERSION,
                "capabilities": {"tools": {}},
                "serverInfo": {"name": SERVER_NAME, "version": SERVER_VERSION},
                "instructions": INSTRUCTIONS,
            },
        )

    if method in ("notifications/initialized", "notifications/cancelled"):
        return None

    if method == "ping":
        return _result(request_id, {})

    if method == "tools/list":
        return _result(request_id, {"tools": TOOLS})

    if method == "resources/list":
        return _result(request_id, {"resources": []})

    if method == "prompts/list":
        return _result(request_id, {"prompts": []})

    if method == "tools/call":
        name = params.get("name")
        arguments = params.get("arguments") or {}
        if not name:
            return _error(request_id, -32602, "A tool name is required")
        if not isinstance(arguments, dict):
            return _error(request_id, -32602, "Tool arguments must be an object")
        try:
            return _result(request_id, call_tool(client, name, arguments))
        except VectorStudioError as exc:
            return _result(
                request_id,
                {
                    "content": [{"type": "text", "text": str(exc)}],
                    "isError": True,
                },
            )
        except Exception as exc:  # pragma: no cover - defensive
            return _error(request_id, -32603, str(exc))

    if request_id is None:
        return None
    return _error(request_id, -32601, f"Method not found: {method}")


def main() -> int:
    client = VectorStudio()
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            message = json.loads(line)
        except json.JSONDecodeError:
            sys.stdout.write(json.dumps(_error(None, -32700, "Invalid JSON-RPC request")) + "\n")
            sys.stdout.flush()
            continue
        response = handle(message, client)
        if response is not None:
            sys.stdout.write(json.dumps(response) + "\n")
            sys.stdout.flush()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
