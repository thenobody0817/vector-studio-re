#!/usr/bin/env python3
"""Live end-to-end check against a running Vector Studio instance.

Start the app with automation enabled, then run:

    python3 tests/e2e_live.py

It exercises the raw RPC broker (capabilities, describe, session.list) and the
open-source MCP bridge (initialize, tools/list, tools/call).
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "client"))

from vector_client import VectorStudio, VectorStudioError  # noqa: E402


def check(label: str, ok: bool, detail: str = "") -> bool:
    print(f"[{'PASS' if ok else 'FAIL'}] {label}{(' - ' + detail) if detail else ''}")
    return ok


def rpc_checks() -> bool:
    client = VectorStudio()
    runtime = client.runtime()
    print(f"broker: port={runtime['port']} pid={runtime['pid']}")

    capabilities = client.capabilities()
    ok = check(
        "capabilities lists operations",
        any(op["id"] == "shape.create" for op in capabilities),
        f"{len(capabilities)} operations",
    )

    described = client.describe("shape.create")
    ok = check("describe returns a schema", "inputSchema" in described) and ok

    sessions = client.session_list()
    ok = check("session.list responds", "sessions" in sessions, json.dumps(sessions)[:120]) and ok

    try:
        client.rpc("does.not.exist")
        ok = check("unknown operation raises", False) and ok
    except VectorStudioError as exc:
        ok = check("unknown operation raises", exc.code == "UNKNOWN_OPERATION", exc.code or "") and ok

    try:
        list(client.events())
        ok = check("event stream is reported as unsupported", False) and ok
    except VectorStudioError as exc:
        ok = check(
            "event stream is reported as unsupported",
            exc.code == "EVENTS_UNSUPPORTED",
            exc.code or "",
        ) and ok

    bare_home = Path(tempfile.mkdtemp(prefix="vector-no-cred-"))
    try:
        # runtime present, credential missing -> the credential error is the one raised
        shutil.copy(Path(client.home) / "runtime.json", bare_home / "runtime.json")
        VectorStudio(home=bare_home).rpc("capabilities")
        ok = check("missing credential raises", False) and ok
    except VectorStudioError as exc:
        ok = check(
            "missing credential raises", "credential" in exc.message.lower(), exc.message[:60]
        ) and ok
    finally:
        shutil.rmtree(bare_home, ignore_errors=True)

    return ok


def mcp_checks() -> bool:
    server = ROOT / "client" / "vector_mcp_server.py"
    requests = [
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {
                "protocolVersion": "2025-11-25",
                "capabilities": {},
                "clientInfo": {"name": "e2e", "version": "0"},
            },
        },
        {"jsonrpc": "2.0", "method": "notifications/initialized"},
        {"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
        {
            "jsonrpc": "2.0",
            "id": 3,
            "method": "tools/call",
            "params": {"name": "vector", "arguments": {"operation": "capabilities"}},
        },
    ]
    proc = subprocess.run(
        [sys.executable, str(server)],
        input="\n".join(json.dumps(r) for r in requests) + "\n",
        capture_output=True,
        text=True,
        timeout=60,
    )
    lines = [json.loads(line) for line in proc.stdout.splitlines() if line.strip()]
    by_id = {msg.get("id"): msg for msg in lines}
    ok = check("mcp initialize", 1 in by_id, str(by_id.get(1, {}).get("error", ""))[:80])
    tools = by_id.get(2, {}).get("result", {}).get("tools", [])
    names = [tool["name"] for tool in tools]
    ok = check("mcp tools/list", "vector" in names and "vector_preview" in names, ", ".join(names)) and ok
    call = by_id.get(3, {}).get("result", {})
    ok = check("mcp tools/call", call.get("isError") is False, json.dumps(call)[:120]) and ok
    if proc.stderr.strip():
        print("server stderr:", proc.stderr.strip()[:400])
    return ok


def main() -> int:
    try:
        ok = rpc_checks()
    except VectorStudioError as exc:
        print(f"broker unavailable: {exc}")
        return 2
    ok = mcp_checks() and ok
    print("ALL PASS" if ok else "FAILURES PRESENT")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
